import 'dart:async';

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/models.dart';
import '../core/theme.dart';
import '../widgets/live_frame_view.dart';
import 'record_detail_page.dart';

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key, required this.state, required this.activeTab});

  final AppState state;
  final ValueNotifier<int> activeTab;

  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  StatsData? _stats;
  CameraStatus? _camera;
  SortRecord? _latest;
  bool _loading = true;
  String? _error;
  int _days = 1;
  String _source = 'device';
  bool _online = false;

  Timer? _timer;
  StreamSubscription<Map<String, dynamic>>? _recordSub;
  StreamSubscription<void>? _frameSub;
  StreamSubscription<bool>? _socketStateSub;
  DateTime _lastReloadAt = DateTime.fromMillisecondsSinceEpoch(0);

  @override
  void initState() {
    super.initState();
    _recordSub = widget.state.realtime.records.listen(_onNewRecord);
    _socketStateSub = widget.state.realtime.connectionState.listen((connected) {
      if (mounted) setState(() => _online = connected);
    });
    widget.activeTab.addListener(_onTabChanged);
    _refreshAll();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (!mounted || widget.activeTab.value != 0) return;
      _loadStats(silent: true);
      _loadCamera();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _recordSub?.cancel();
    _frameSub?.cancel();
    _socketStateSub?.cancel();
    widget.activeTab.removeListener(_onTabChanged);
    super.dispose();
  }

  void _onTabChanged() {
    if (!mounted) return;
    setState(() {});
    if (widget.activeTab.value == 0) {
      _loadStats(silent: true);
      _loadCamera();
    }
  }

  Future<void> _refreshAll() async {
    await Future.wait([_loadStats(), _loadCamera(), _loadLatest()]);
  }

  void _onNewRecord(Map<String, dynamic> json) {
    final record = SortRecord.fromJson(json);
    if (!mounted) return;
    setState(() => _latest = record);
    final now = DateTime.now();
    if (now.difference(_lastReloadAt).inSeconds >= 4) {
      _lastReloadAt = now;
      _loadStats(silent: true);
    }
  }

  Future<void> _loadStats({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      final stats = await widget.state.api.stats(days: _days);
      if (!mounted) return;
      setState(() {
        _stats = stats;
        _error = null;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        if (!silent) _error = e.message;
        _loading = false;
      });
    }
  }

  Future<void> _loadCamera() async {
    try {
      final status = await widget.state.api.cameraStatus();
      if (!mounted) return;
      setState(() => _camera = status);
    } catch (_) {
      // 摄像头状态失败不影响看板主体
    }
  }

  Future<void> _loadLatest() async {
    try {
      final record = await widget.state.api.latestRecord();
      if (!mounted) return;
      setState(() => _latest = record);
    } catch (_) {}
  }

  String get _streamUrl {
    final base = widget.state.baseUrl.replaceAll(RegExp(r'/+$'), '');
    final path = _source == 'device' ? '/api/device/stream' : '/api/device/live';
    final token = Uri.encodeComponent(widget.state.token ?? '');
    return '$base$path?token=$token';
  }

  String get _todayText {
    const weekdays = ['一', '二', '三', '四', '五', '六', '日'];
    final now = DateTime.now();
    return '${now.month}月${now.day}日 · 星期${weekdays[now.weekday - 1]}';
  }

  @override
  Widget build(BuildContext context) {
    final stats = _stats;
    return SafeArea(
      bottom: false,
      child: RefreshIndicator(
        color: AppColors.primary,
        onRefresh: _refreshAll,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
          children: [
            _buildHeader(stats),
            if (_error != null) ...[
              const SizedBox(height: 14),
              _buildErrorCard(),
            ],
            const SizedBox(height: 16),
            _buildTrendCard(stats),
            const SizedBox(height: 16),
            _buildTypeCard(stats),
            const SizedBox(height: 16),
            _buildLiveCard(),
            const SizedBox(height: 16),
            _buildLatestCard(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(StatsData? stats) {
    final total = stats?.todayTotal ?? 0;
    final good = stats?.todayGood ?? 0;
    final bad = stats?.todayBad ?? 0;
    final rate = stats?.goodRate ?? 0;

    return Container(
      padding: const EdgeInsets.fromLTRB(18, 16, 18, 18),
      decoration: BoxDecoration(
        gradient: AppColors.headerGradient,
        borderRadius: BorderRadius.circular(22),
        boxShadow: [
          BoxShadow(
            color: AppColors.primaryDark.withValues(alpha: 0.25),
            blurRadius: 24,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            color: _online ? const Color(0xFF4ADE80) : const Color(0xFFCBD5E1),
                            shape: BoxShape.circle,
                            boxShadow: _online
                                ? [
                                    BoxShadow(
                                      color: const Color(0xFF4ADE80).withValues(alpha: 0.6),
                                      blurRadius: 8,
                                    ),
                                  ]
                                : null,
                          ),
                        ),
                        const SizedBox(width: 6),
                        Text(
                          _online ? '实时通道已连接' : '实时通道未连接',
                          style: TextStyle(color: Colors.white.withValues(alpha: 0.85), fontSize: 12),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    Text('今日分拣', style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 13, letterSpacing: 1)),
                    const SizedBox(height: 2),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          '$total',
                          style: const TextStyle(color: Colors.white, fontSize: 42, fontWeight: FontWeight.w800, height: 1.05),
                        ),
                        Padding(
                          padding: const EdgeInsets.only(left: 6, bottom: 7),
                          child: Text('颗', style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 14)),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    _todayText,
                    style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 12),
                  ),
                  const SizedBox(height: 8),
                  InkWell(
                    onTap: _refreshAll,
                    borderRadius: BorderRadius.circular(20),
                    child: Container(
                      padding: const EdgeInsets.all(7),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.18),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.refresh, color: Colors.white, size: 18),
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 16),
          Container(height: 1, color: Colors.white.withValues(alpha: 0.18)),
          const SizedBox(height: 14),
          Row(
            children: [
              _headerMetric('合格', '$good', const Color(0xFF86EFAC)),
              _headerDivider(),
              _headerMetric('剔除', '$bad', const Color(0xFFFCA5A5)),
              _headerDivider(),
              _headerMetric('合格率', '${rate.toStringAsFixed(1)}%', Colors.white),
            ],
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: (rate / 100).clamp(0.0, 1.0),
              minHeight: 6,
              backgroundColor: Colors.white.withValues(alpha: 0.22),
              valueColor: const AlwaysStoppedAnimation(Color(0xFF4ADE80)),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            total == 0 ? '今天还没有分拣记录' : '合格率按今日累计计算',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 11.5),
          ),
        ],
      ),
    );
  }

  Widget _headerMetric(String label, String value, Color color) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 11.5)),
          const SizedBox(height: 3),
          Text(value, style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w700, height: 1.1)),
        ],
      ),
    );
  }

  Widget _headerDivider() {
    return Container(
      width: 1,
      height: 30,
      margin: const EdgeInsets.symmetric(horizontal: 10),
      color: Colors.white.withValues(alpha: 0.18),
    );
  }

  Widget _buildErrorCard() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFFFECACA)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_outlined, color: AppColors.bad, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: Text(_error!, style: const TextStyle(color: AppColors.bad, fontSize: 12.5, height: 1.4)),
          ),
          TextButton(onPressed: _refreshAll, child: const Text('重试')),
        ],
      ),
    );
  }

  Widget _buildTrendCard(StatsData? stats) {
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionTitle(
            title: '分拣趋势',
            trailing: _loading
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary),
                  )
                : null,
          ),
          Row(
            children: [
              _segment('24小时', 1),
              const SizedBox(width: 8),
              _segment('7天', 7),
              const SizedBox(width: 8),
              _segment('30天', 30),
              const Spacer(),
              _legendDot(AppColors.primary, '总量'),
              const SizedBox(width: 10),
              _legendDot(AppColors.good, '合格'),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(height: 168, child: _chart(stats)),
          const SizedBox(height: 4),
        ],
      ),
    );
  }

  Widget _segment(String text, int days) {
    final active = _days == days;
    return GestureDetector(
      onTap: () {
        if (_days == days) return;
        setState(() => _days = days);
        _loadStats();
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: active ? AppColors.primary : const Color(0xFFF1F5F9),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          text,
          style: TextStyle(
            fontSize: 12,
            fontWeight: active ? FontWeight.w600 : FontWeight.w500,
            color: active ? Colors.white : AppColors.subtle,
          ),
        ),
      ),
    );
  }

  Widget _legendDot(Color color, String label) {
    return Row(
      children: [
        Container(width: 7, height: 7, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 5),
        Text(label, style: const TextStyle(fontSize: 11, color: AppColors.subtle)),
      ],
    );
  }

  Widget _chart(StatsData? stats) {
    if (stats == null || stats.labels.isEmpty) {
      return const EmptyHint(text: '暂无趋势数据', icon: Icons.show_chart);
    }

    final labels = stats.labels;
    final total = stats.totalSeries;
    final good = stats.goodSeries;
    final maxValue = stats.maxSeries;
    final maxY = maxValue <= 4 ? 4.0 : (maxValue * 1.25).ceilToDouble();
    var interval = (maxY / 4).ceilToDouble();
    if (interval < 1) interval = 1;

    final bottomStep = labels.length <= 8 ? 1 : (labels.length / 6).ceil();

    return LineChart(
      LineChartData(
        minX: 0,
        maxX: (labels.length - 1).toDouble(),
        minY: 0,
        maxY: maxY,
        clipData: const FlClipData.all(),
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: interval,
          getDrawingHorizontalLine: (value) => const FlLine(color: AppColors.line, strokeWidth: 1),
        ),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 30,
              interval: interval,
              getTitlesWidget: (value, meta) {
                if (value == meta.max && value % interval != 0) return const SizedBox.shrink();
                return SideTitleWidget(
                  axisSide: meta.axisSide,
                  space: 6,
                  child: Text(
                    value.toInt().toString(),
                    style: const TextStyle(fontSize: 10, color: AppColors.subtle),
                  ),
                );
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 24,
              interval: 1,
              getTitlesWidget: (value, meta) {
                final index = value.toInt();
                if (index < 0 || index >= labels.length) return const SizedBox.shrink();
                if (index % bottomStep != 0 && index != labels.length - 1) {
                  return const SizedBox.shrink();
                }
                return SideTitleWidget(
                  axisSide: meta.axisSide,
                  space: 6,
                  child: Text(
                    labels[index],
                    style: const TextStyle(fontSize: 9.5, color: AppColors.subtle),
                  ),
                );
              },
            ),
          ),
        ),
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (spot) => const Color(0xFF0F172A),
            getTooltipItems: (spots) {
              return spots.map((spot) {
                final isTotal = spot.barIndex == 0;
                return LineTooltipItem(
                  '${isTotal ? '总量' : '合格'} ${spot.y.toInt()}',
                  const TextStyle(color: Colors.white, fontSize: 11),
                );
              }).toList();
            },
          ),
        ),
        lineBarsData: [
          _lineData(total.map((e) => e.toDouble()).toList(), AppColors.primary, withArea: true),
          _lineData(good.map((e) => e.toDouble()).toList(), AppColors.good, withArea: false),
        ],
      ),
    );
  }

  LineChartBarData _lineData(List<double> values, Color color, {required bool withArea}) {
    final spots = <FlSpot>[];
    for (var i = 0; i < values.length; i++) {
      spots.add(FlSpot(i.toDouble(), values[i]));
    }
    return LineChartBarData(
      spots: spots,
      isCurved: true,
      curveSmoothness: 0.25,
      color: color,
      barWidth: 2.4,
      isStrokeCapRound: true,
      dotData: const FlDotData(show: false),
      belowBarData: BarAreaData(
        show: withArea,
        color: color.withValues(alpha: 0.12),
      ),
    );
  }

  Widget _buildTypeCard(StatsData? stats) {
    final items = stats?.byType ?? const <FruitTypeCount>[];
    var maxCount = 1;
    for (final item in items) {
      if (item.count > maxCount) maxCount = item.count;
    }

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionTitle(title: '品种分布', subtitle: '今日累计'),
          if (items.isEmpty)
            const EmptyHint(text: '今天还没有分拣记录', icon: Icons.eco_outlined)
          else
            ...items.map((item) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            item.name,
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.ink),
                          ),
                        ),
                        Text(
                          '${item.count} 颗',
                          style: const TextStyle(fontSize: 12, color: AppColors.subtle),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(6),
                      child: LinearProgressIndicator(
                        value: item.count / maxCount,
                        minHeight: 6,
                        backgroundColor: const Color(0xFFEFF4FB),
                        valueColor: const AlwaysStoppedAnimation(AppColors.accent),
                      ),
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }

  Widget _buildLiveCard() {
    final camera = _camera;
    final running = camera?.running ?? false;

    return AppCard(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(child: SectionTitle(title: '实时画面')),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: running ? const Color(0xFFECFDF5) : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  running ? '后端摄像头运行中' : '看设备上传画面',
                  style: TextStyle(
                    fontSize: 10.5,
                    color: running ? AppColors.good : AppColors.subtle,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              _sourceChip('设备上传流', 'device'),
              const SizedBox(width: 8),
              _sourceChip('后端摄像头', 'backend'),
            ],
          ),
          const SizedBox(height: 10),
          LiveFrameView(
            url: _streamUrl,
            enabled: widget.activeTab.value == 0,
            height: 200,
            emptyText: '切到「看板」页后自动取流',
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              const Icon(Icons.info_outline, size: 13, color: AppColors.subtle),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  _source == 'device'
                      ? '读取 OpenMV / 采集脚本上传的最新帧'
                      : '读取后端直连摄像头的最新帧',
                  style: const TextStyle(fontSize: 11, color: AppColors.subtle),
                ),
              ),
              if (camera != null && camera.width > 0)
                Text(
                  '${camera.width}×${camera.height}',
                  style: const TextStyle(fontSize: 11, color: AppColors.subtle),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _sourceChip(String label, String value) {
    final active = _source == value;
    return GestureDetector(
      onTap: () {
        if (_source == value) return;
        setState(() => _source = value);
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: active ? const Color(0xFFEFF6FF) : const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: active ? const Color(0xFFBFDBFE) : AppColors.line),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 11.5,
            color: active ? AppColors.primaryDark : AppColors.subtle,
            fontWeight: active ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }

  Widget _buildLatestCard() {
    final record = _latest;
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionTitle(title: '最新识别'),
          if (record == null)
            const EmptyHint(text: '还没有识别记录', icon: Icons.center_focus_weak)
          else
            InkWell(
              onTap: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => RecordDetailPage(state: widget.state, record: record),
                  ),
                );
              },
              borderRadius: BorderRadius.circular(12),
              child: Row(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: SizedBox(
                      width: 72,
                      height: 72,
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
                            _resultBadge(record),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          '${record.createTime}  ·  置信度 ${record.confidencePercent}%',
                          style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Text(
                              '面积 ${record.area} px',
                              style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
                            ),
                            const Spacer(),
                            const Text('查看详情', style: TextStyle(fontSize: 11.5, color: AppColors.primary)),
                            const Icon(Icons.chevron_right, size: 15, color: AppColors.primary),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _resultBadge(SortRecord record) {
    final color = record.isGood ? AppColors.good : AppColors.bad;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        record.resultText,
        style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600),
      ),
    );
  }
}
