import 'package:flutter/material.dart';

import '../core/api_client.dart';
import '../core/theme.dart';

/// 修改后端服务器地址的底部弹窗，返回用户确认后的地址
Future<String?> showServerSettingsSheet(BuildContext context, {required String current}) {
  return showModalBottomSheet<String>(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (_) => _ServerSettingsSheet(current: current),
  );
}

class _ServerSettingsSheet extends StatefulWidget {
  const _ServerSettingsSheet({required this.current});

  final String current;

  @override
  State<_ServerSettingsSheet> createState() => _ServerSettingsSheetState();
}

class _ServerSettingsSheetState extends State<_ServerSettingsSheet> {
  late final TextEditingController _controller;
  bool _testing = false;
  String? _testMessage;
  bool _testOk = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.current);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  String get _normalized {
    var url = _controller.text.trim();
    if (url.isEmpty) return url;
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'http://$url';
    return url.replaceAll(RegExp(r'/+$'), '');
  }

  Future<void> _test() async {
    final url = _normalized;
    if (url.isEmpty) {
      setState(() {
        _testOk = false;
        _testMessage = '请先填写服务器地址';
      });
      return;
    }
    setState(() {
      _testing = true;
      _testMessage = null;
    });
    final client = ApiClient(baseUrl: url);
    try {
      final service = await client.checkHealth();
      if (!mounted) return;
      setState(() {
        _testOk = true;
        _testMessage = '连接成功：$service';
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _testOk = false;
        _testMessage = e.message;
      });
    } finally {
      if (mounted) setState(() => _testing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    return Container(
      padding: EdgeInsets.fromLTRB(20, 14, 20, 20 + bottomInset),
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 38,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.line,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Text('服务器地址', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text(
            '填写运行后端的那台电脑的局域网地址，例如 http://192.168.1.8:5000',
            style: TextStyle(fontSize: 12.5, color: AppColors.subtle, height: 1.5),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _controller,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(
              hintText: 'http://10.153.180.220:5000',
              prefixIcon: Icon(Icons.dns_outlined),
            ),
            onChanged: (_) => setState(() => _testMessage = null),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              OutlinedButton.icon(
                onPressed: _testing ? null : _test,
                icon: _testing
                    ? const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.wifi_tethering, size: 18),
                label: const Text('测试连接'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: AppColors.primary,
                  side: const BorderSide(color: AppColors.primary),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _testMessage == null
                    ? const SizedBox.shrink()
                    : Text(
                        _testMessage!,
                        style: TextStyle(
                          fontSize: 12,
                          color: _testOk ? AppColors.good : AppColors.bad,
                          height: 1.4,
                        ),
                      ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () {
                final url = _normalized;
                if (url.isEmpty) {
                  Navigator.of(context).pop();
                  return;
                }
                Navigator.of(context).pop(url);
              },
              child: const Text('保存'),
            ),
          ),
        ],
      ),
    );
  }
}
