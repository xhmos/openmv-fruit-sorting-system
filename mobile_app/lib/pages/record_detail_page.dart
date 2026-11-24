import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/models.dart';
import '../core/theme.dart';

class RecordDetailPage extends StatelessWidget {
  const RecordDetailPage({super.key, required this.state, required this.record});

  final AppState state;
  final SortRecord record;

  Future<void> _delete(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除记录'),
        content: const Text('删除后记录与图片都会从服务器清理，无法恢复。'),
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
    if (confirmed != true) return;

    try {
      await state.api.deleteRecord(record.id);
      if (context.mounted) Navigator.of(context).pop(true);
    } on ApiException catch (e) {
      if (context.mounted) toast(context, e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = record.isGood ? AppColors.good : AppColors.bad;
    final imageUrl = state.api.absolute(record.imgUrl);

    return Scaffold(
      appBar: AppBar(
        title: const Text('记录详情', style: TextStyle(fontWeight: FontWeight.w700)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
        children: [
          Container(
            height: 260,
            decoration: BoxDecoration(
              color: const Color(0xFF0B1220),
              borderRadius: BorderRadius.circular(18),
            ),
            clipBehavior: Clip.antiAlias,
            child: imageUrl.isEmpty
                ? const Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.image_not_supported_outlined, color: Colors.white38, size: 38),
                        SizedBox(height: 8),
                        Text('这条记录没有保存图片', style: TextStyle(color: Colors.white54, fontSize: 12)),
                      ],
                    ),
                  )
                : InteractiveViewer(
                    minScale: 1,
                    maxScale: 4,
                    child: Image.network(
                      imageUrl,
                      fit: BoxFit.contain,
                      errorBuilder: (_, __, ___) => const Center(
                        child: Text('图片加载失败', style: TextStyle(color: Colors.white54, fontSize: 12)),
                      ),
                    ),
                  ),
          ),
          const SizedBox(height: 16),
          AppCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        record.fruitType.isEmpty ? '未知品种' : record.fruitType,
                        style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.ink),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: Text(
                        record.resultText,
                        style: TextStyle(fontSize: 13, color: color, fontWeight: FontWeight.w700),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                _row('置信度', '${record.confidencePercent}%'),
                _row('检测面积', '${record.area} px'),
                _row('识别时间', record.createTime),
                _row('记录编号', '#${record.id}'),
                _row('截图路径', record.imgUrl.isEmpty ? '未保存' : record.imgUrl),
              ],
            ),
          ),
          if (state.user?.isAdmin == true) ...[
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: () => _delete(context),
              icon: const Icon(Icons.delete_outline, size: 18),
              label: const Text('删除这条记录'),
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.bad,
                side: const BorderSide(color: Color(0xFFFCA5A5)),
                minimumSize: const Size(0, 48),
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 76,
            child: Text(label, style: const TextStyle(fontSize: 13, color: AppColors.subtle)),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontSize: 13, color: AppColors.ink, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}
