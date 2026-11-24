import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/theme.dart';

class ParamsPage extends StatefulWidget {
  const ParamsPage({super.key, required this.state});

  final AppState state;

  @override
  State<ParamsPage> createState() => _ParamsPageState();
}

class _ParamsPageState extends State<ParamsPage> {
  static const _groups = [
    {
      'title': '色相 H',
      'desc': '决定识别哪种颜色区间，OpenMV 的 HSV 色相范围是 0~179',
      'keys': ['h_min', 'h_max'],
      'min': 0,
      'max': 179,
    },
    {
      'title': '饱和度 S',
      'desc': '颜色浓度，太低会把浅色果实滤掉',
      'keys': ['s_min', 's_max'],
      'min': 0,
      'max': 255,
    },
    {
      'title': '亮度 V',
      'desc': '明暗程度，光照变化大时需要重新标定',
      'keys': ['v_min', 'v_max'],
      'min': 0,
      'max': 255,
    },
  ];

  final Map<String, TextEditingController> _controllers = {};
  bool _loading = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.state.api.settings();
      if (!mounted) return;
      setState(() {
        for (final item in items) {
          _controllers[item.key] = TextEditingController(text: item.value);
        }
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

  int? _valueOf(String key) => int.tryParse(_controllers[key]?.text.trim() ?? '');

  Future<void> _save() async {
    FocusScope.of(context).unfocus();
    final settings = <String, int>{};
    for (final key in [
      'h_min', 'h_max', 's_min', 's_max', 'v_min', 'v_max', 'min_area',
    ]) {
      final controller = _controllers[key];
      if (controller == null) continue;
      final value = int.tryParse(controller.text.trim());
      if (value == null) {
        toast(context, '请把 $key 填成整数');
        return;
      }
      settings[key] = value;
    }

    if ((settings['h_min'] ?? 0) > (settings['h_max'] ?? 0)) {
      toast(context, '色相最小值不能大于最大值');
      return;
    }
    if ((settings['s_min'] ?? 0) > (settings['s_max'] ?? 0)) {
      toast(context, '饱和度最小值不能大于最大值');
      return;
    }
    if ((settings['v_min'] ?? 0) > (settings['v_max'] ?? 0)) {
      toast(context, '亮度最小值不能大于最大值');
      return;
    }

    setState(() => _saving = true);
    try {
      await widget.state.api.updateSettings(settings);
      if (mounted) toast(context, '参数已保存，OpenMV 下次拉取时生效');
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = widget.state.user?.isAdmin ?? false;

    return Scaffold(
      appBar: AppBar(title: const Text('识别参数', style: TextStyle(fontWeight: FontWeight.w700))),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppColors.primary))
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      EmptyHint(text: _error!, icon: Icons.cloud_off_outlined),
                      OutlinedButton(onPressed: _load, child: const Text('重试')),
                    ],
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                  children: [
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: const Color(0xFFEFF6FF),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.tips_and_updates_outlined, size: 18, color: AppColors.primaryDark),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              isAdmin
                                  ? '这些参数由 OpenMV 定时拉取，保存后下一次拉取就会生效。改色相/饱和度/亮度前建议先在网页端调试确认。'
                                  : '当前账号是操作员，只能查看参数，修改需要管理员权限。',
                              style: const TextStyle(fontSize: 12, color: AppColors.primaryDark, height: 1.5),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                    ..._groups.map((group) => _groupCard(group, isAdmin)),
                    _areaCard(isAdmin),
                    if (isAdmin) ...[
                      const SizedBox(height: 8),
                      FilledButton(
                        onPressed: _saving ? null : _save,
                        child: _saving
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                              )
                            : const Text('保存参数'),
                      ),
                    ],
                  ],
                ),
    );
  }

  Widget _groupCard(Map<String, Object> group, bool isAdmin) {
    final keys = (group['keys'] as List).cast<String>();
    final min = group['min'] as int;
    final max = group['max'] as int;

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: AppCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${group['title']}',
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.ink),
            ),
            const SizedBox(height: 4),
            Text('${group['desc']}', style: const TextStyle(fontSize: 11.5, color: AppColors.subtle, height: 1.4)),
            const SizedBox(height: 12),
            Row(
              children: [
                for (var i = 0; i < keys.length; i++) ...[
                  if (i > 0) const SizedBox(width: 12),
                  Expanded(
                    child: _numberField(
                      key: keys[i],
                      label: keys[i].endsWith('_min') ? '最小值' : '最大值',
                      hint: '$min~$max',
                      enabled: isAdmin,
                    ),
                  ),
                ],
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _areaCard(bool isAdmin) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '最小识别面积',
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.ink),
          ),
          const SizedBox(height: 4),
          const Text(
            '小于这个像素面积的色块会被当作噪点忽略，一般 300~1500 之间比较合适',
            style: TextStyle(fontSize: 11.5, color: AppColors.subtle, height: 1.4),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _numberField(
                  key: 'min_area',
                  label: '面积阈值',
                  hint: '0~1000000',
                  enabled: isAdmin,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  '当前值：${_valueOf('min_area') ?? '—'} px',
                  style: const TextStyle(fontSize: 12, color: AppColors.subtle),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _numberField({required String key, required String label, required String hint, required bool enabled}) {
    final controller = _controllers[key];
    if (controller == null) {
      return TextField(
        enabled: false,
        decoration: InputDecoration(labelText: label, hintText: '服务器未配置该参数'),
      );
    }
    return TextField(
      controller: controller,
      enabled: enabled,
      keyboardType: TextInputType.number,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly],
      decoration: InputDecoration(labelText: label, hintText: hint),
      onChanged: (_) => setState(() {}),
    );
  }
}
