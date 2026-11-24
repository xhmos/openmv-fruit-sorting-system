import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/models.dart';
import '../core/theme.dart';
import 'record_detail_page.dart';

class RecordsPage extends StatefulWidget {
  const RecordsPage({super.key, required this.state});

  final AppState state;

  @override
  State<RecordsPage> createState() => _RecordsPageState();
}

class _RecordsPageState extends State<RecordsPage> {
  final ScrollController _scroll = ScrollController();
  final List<SortRecord> _items = [];

  bool _loading = false;
  bool _loadingMore = false;
  String? _error;
  int _page = 1;
  int _pages = 1;
  int _total = 0;
  String _result = '';
  String _fruitType = '';
  List<String> _types = const [];

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _loadTypes();
    _loadFirst();
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scroll.hasClients) return;
    if (_scroll.position.pixels >= _scroll.position.maxScrollExtent - 240) {
      _loadMore();
    }
  }

  Future<void> _loadTypes() async {
    try {
      final stats = await widget.state.api.stats(days: 7);
      if (!mounted) return;
      setState(() => _types = stats.byType.map((e) => e.name).where((e) => e.isNotEmpty).toList());
    } catch (_) {}
  }

  Future<void> _loadFirst() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.state.api.records(
        page: 1,
        pageSize: 15,
        fruitType: _fruitType,
        result: _result,
      );
      if (!mounted) return;
      final items = asMapList(data['items']).map(SortRecord.fromJson).toList();
      setState(() {
        _items
          ..clear()
          ..addAll(items);
        _page = 1;
        _pages = asInt(data['pages'], 1);
        _total = asInt(data['total']);
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_loadingMore || _loading || _page >= _pages) return;
    setState(() => _loadingMore = true);
    try {
      final next = _page + 1;
      final data = await widget.state.api.records(
        page: next,
        pageSize: 15,
        fruitType: _fruitType,
        result: _result,
      );
      if (!mounted) return;
      final items = asMapList(data['items']).map(SortRecord.fromJson).toList();
      setState(() {
        _items.addAll(items);
        _page = next;
        _pages = asInt(data['pages'], next);
        _total = asInt(data['total'], _total);
        _loadingMore = false;
      });
    } catch (_) {
      if (mounted) setState(() => _loadingMore = false);
    }
  }

  Future<void> _confirmDelete(SortRecord record) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除记录'),
        content: Text('确定删除 ${record.fruitType} 的这条记录吗？图片也会一并清理。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('取消')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppColors.bad),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await widget.state.api.deleteRecord(record.id);
      if (!mounted) return;
      toast(context, '已删除');
      _loadFirst();
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = widget.state.user?.isAdmin ?? false;

    return SafeArea(
      bottom: false,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: Row(
              children: [
                const Text('分拣记录', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.ink)),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFFEFF6FF),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '共 $_total 条',
                    style: const TextStyle(fontSize: 11.5, color: AppColors.primaryDark),
                  ),
                ),
                const Spacer(),
                IconButton(
                  tooltip: '刷新',
                  onPressed: _loadFirst,
                  icon: const Icon(Icons.refresh, color: AppColors.subtle),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                _resultChip('全部', ''),
                const SizedBox(width: 8),
                _resultChip('合格', 'good'),
                const SizedBox(width: 8),
                _resultChip('剔除', 'bad'),
                const Spacer(),
                PopupMenuButton<String>(
                  tooltip: '按品种筛选',
                  onSelected: (value) {
                    setState(() => _fruitType = value);
                    _loadFirst();
                  },
                  itemBuilder: (context) => [
                    const PopupMenuItem(value: '', child: Text('全部品种')),
                    ..._types.map((e) => PopupMenuItem(value: e, child: Text(e))),
                  ],
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF8FAFC),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppColors.line),
                    ),
                    child: Row(
                      children: [
                        Text(
                          _fruitType.isEmpty ? '全部品种' : _fruitType,
                          style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
                        ),
                        const Icon(Icons.arrow_drop_down, size: 16, color: AppColors.subtle),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: RefreshIndicator(
              color: AppColors.primary,
              onRefresh: _loadFirst,
              child: _buildList(isAdmin),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildList(bool isAdmin) {
    if (_loading && _items.isEmpty) {
      return const Center(child: CircularProgressIndicator(color: AppColors.primary));
    }
    if (_error != null && _items.isEmpty) {
      return ListView(
        children: [
          const SizedBox(height: 60),
          EmptyHint(text: _error!, icon: Icons.cloud_off_outlined),
          Center(
            child: OutlinedButton(onPressed: _loadFirst, child: const Text('重试')),
          ),
        ],
      );
    }
    if (_items.isEmpty) {
      return ListView(
        children: const [
          SizedBox(height: 60),
          EmptyHint(text: '没有符合条件的记录', icon: Icons.inbox_outlined),
        ],
      );
    }

    return ListView.separated(
      controller: _scroll,
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
      itemCount: _items.length + 1,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        if (index == _items.length) return _buildFooter();
        final record = _items[index];
        return _recordCard(record, isAdmin);
      },
    );
  }

  Widget _buildFooter() {
    if (_loadingMore) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 16),
        child: Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2.2, color: AppColors.primary),
          ),
        ),
      );
    }
    if (_page < _pages) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Center(
          child: Text(
            '上滑加载更多（$_page/$_pages）',
            style: const TextStyle(fontSize: 12, color: AppColors.subtle),
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Center(
        child: Text(
          '已加载全部 $_total 条记录',
          style: const TextStyle(fontSize: 12, color: AppColors.subtle),
        ),
      ),
    );
  }

  Widget _recordCard(SortRecord record, bool isAdmin) {
    final color = record.isGood ? AppColors.good : AppColors.bad;
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF0F172A).withValues(alpha: 0.05),
            blurRadius: 14,
            offset: const Offset(0, 5),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () async {
            final deleted = await Navigator.of(context).push<bool>(
              MaterialPageRoute<bool>(builder: (_) => RecordDetailPage(state: widget.state, record: record)),
            );
            if (deleted == true) _loadFirst();
          },
          onLongPress: isAdmin ? () => _confirmDelete(record) : null,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(12),
                  child: SizedBox(
                    width: 78,
                    height: 78,
                    child: record.imgUrl.isEmpty
                        ? Container(
                            color: const Color(0xFFF1F5F9),
                            child: const Icon(Icons.image_outlined, color: AppColors.subtle, size: 26),
                          )
                        : Image.network(
                            widget.state.api.absolute(record.imgUrl),
                            fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => Container(
                              color: const Color(0xFFF1F5F9),
                              child: const Icon(Icons.broken_image_outlined, color: AppColors.subtle, size: 26),
                            ),
                          ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              record.fruitType.isEmpty ? '未知品种' : record.fruitType,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.ink),
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: color.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Text(
                              record.resultText,
                              style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 7),
                      Row(
                        children: [
                          const Icon(Icons.schedule, size: 13, color: AppColors.subtle),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              record.createTime,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 7),
                      Row(
                        children: [
                          _miniTag('置信度 ${record.confidencePercent}%'),
                          const SizedBox(width: 6),
                          _miniTag('面积 ${record.area}'),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _miniTag(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: const TextStyle(fontSize: 10.5, color: AppColors.subtle)),
    );
  }

  Widget _resultChip(String label, String value) {
    final active = _result == value;
    return GestureDetector(
      onTap: () {
        if (_result == value) return;
        setState(() => _result = value);
        _loadFirst();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 160),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 6),
        decoration: BoxDecoration(
          color: active ? AppColors.primary : const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: active ? AppColors.primary : AppColors.line),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            color: active ? Colors.white : AppColors.subtle,
            fontWeight: active ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }
}
