import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/models.dart';
import '../core/theme.dart';

class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key, required this.state});

  final AppState state;

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  CameraStatus? _camera;
  List<SavedDevice> _devices = const [];
  List<VideoItem> _videos = const [];
  bool _busy = false;
  bool _loadingDevices = false;
  bool _loadingVideos = false;
  bool _videosExpanded = false;

  @override
  void initState() {
    super.initState();
    _loadCamera();
    _loadDevices();
  }

  Future<void> _loadCamera() async {
    try {
      final status = await widget.state.api.cameraStatus();
      if (!mounted) return;
      setState(() => _camera = status);
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    }
  }

  Future<void> _loadDevices() async {
    setState(() => _loadingDevices = true);
    try {
      final items = await widget.state.api.savedDevices();
      if (!mounted) return;
      setState(() {
        _devices = items;
        _loadingDevices = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _loadingDevices = false);
      toast(context, e.message);
    }
  }

  Future<void> _loadVideos() async {
    setState(() => _loadingVideos = true);
    try {
      final items = await widget.state.api.videos();
      if (!mounted) return;
      setState(() {
        _videos = items;
        _loadingVideos = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _loadingVideos = false);
      toast(context, e.message);
    }
  }

  Future<void> _toggleCamera(bool start) async {
    if (_busy) return;
    if (start) {
      final options = await _showStartDialog();
      if (options == null) return;
      setState(() => _busy = true);
      try {
        final status = await widget.state.api.startCamera(
          source: '${options['source'] ?? ''}',
          fps: options['fps'] as int,
          detect: options['detect'] as bool,
          snapshot: options['snapshot'] as bool,
          record: options['record'] as bool,
        );
        if (!mounted) return;
        setState(() => _camera = status);
        toast(context, status.running ? '采集已启动' : (status.error.isEmpty ? '启动超时' : status.error));
      } on ApiException catch (e) {
        if (mounted) toast(context, e.message);
      } finally {
        if (mounted) setState(() => _busy = false);
      }
    } else {
      setState(() => _busy = true);
      try {
        final status = await widget.state.api.stopCamera();
        if (!mounted) return;
        setState(() => _camera = status);
        toast(context, '采集已停止');
      } on ApiException catch (e) {
        if (mounted) toast(context, e.message);
      } finally {
        if (mounted) setState(() => _busy = false);
      }
    }
  }

  Future<Map<String, dynamic>?> _showStartDialog() async {
    final sourceCtrl = TextEditingController(
      text: _devices.where((d) => d.devType == 'camera').isNotEmpty
          ? _devices.firstWhere((d) => d.devType == 'camera').target
          : '0',
    );
    final fpsCtrl = TextEditingController(text: '${_camera?.fps ?? 8}');
    bool detect = _camera?.detect ?? true;
    bool snapshot = _camera?.snapshot ?? true;
    bool record = _camera?.record ?? false;

    final result = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocal) => AlertDialog(
          title: const Text('启动摄像头采集'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: sourceCtrl,
                  decoration: const InputDecoration(
                    labelText: '摄像头序号 / 名称',
                    hintText: '0 表示第一个摄像头',
                  ),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: fpsCtrl,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                  decoration: const InputDecoration(labelText: '采集帧率 (fps)'),
                ),
                const SizedBox(height: 6),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: detect,
                  onChanged: (v) => setLocal(() => detect = v),
                  title: const Text('识别果实', style: TextStyle(fontSize: 14)),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: snapshot,
                  onChanged: (v) => setLocal(() => snapshot = v),
                  title: const Text('命中存图并写记录', style: TextStyle(fontSize: 14)),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: record,
                  onChanged: (v) => setLocal(() => record = v),
                  title: const Text('命中另存短视频', style: TextStyle(fontSize: 14)),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('取消')),
            FilledButton(
              onPressed: () {
                final fps = int.tryParse(fpsCtrl.text.trim()) ?? 8;
                Navigator.pop(context, <String, dynamic>{
                  'source': sourceCtrl.text.trim(),
                  'fps': fps.clamp(1, 30),
                  'detect': detect,
                  'snapshot': snapshot,
                  'record': record,
                });
              },
              child: const Text('启动'),
            ),
          ],
        ),
      ),
    );

    sourceCtrl.dispose();
    fpsCtrl.dispose();
    return result;
  }

  Future<void> _toggleSwitch(String key, bool value) async {
    setState(() => _busy = true);
    try {
      final status = await widget.state.api.updateCameraConfig({key: value});
      if (!mounted) return;
      setState(() => _camera = status);
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connectDevice(SavedDevice device) async {
    setState(() => _busy = true);
    try {
      final data = await widget.state.api.connectDevice(device.id);
      if (!mounted) return;
      final message = '${asMap(data['probe'])['message'] ?? ''}';
      toast(context, message.isEmpty ? '已发起连接' : message);
      _loadDevices();
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _deleteDevice(SavedDevice device) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除设备'),
        content: Text('从「我的设备」里移除「${device.name}」？系统里的驱动不受影响。'),
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
      await widget.state.api.deleteDevice(device.id);
      if (!mounted) return;
      toast(context, '已删除');
      _loadDevices();
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    }
  }

  Future<void> _showAddDevice() async {
    final targetCtrl = TextEditingController();
    final nameCtrl = TextEditingController();
    var type = 'camera';
    var submitting = false;

    await showDialog<void>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setLocal) {
          Future<void> submit() async {
            if (submitting) return;
            if (targetCtrl.text.trim().isEmpty) {
              toast(context, '请填写设备目标，例如 0 / COM7 / http://...');
              return;
            }
            setLocal(() => submitting = true);
            try {
              await widget.state.api.addDevice(
                devType: type,
                target: targetCtrl.text.trim(),
                name: nameCtrl.text.trim(),
                note: '',
              );
              if (!context.mounted) return;
              Navigator.pop(context);
              toast(this.context, '设备已添加');
              _loadDevices();
            } on ApiException catch (e) {
              if (!context.mounted) return;
              setLocal(() => submitting = false);
              toast(context, e.message);
            }
          }

          return AlertDialog(
            title: const Text('添加设备'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8,
                    children: [
                      _typeChip('摄像头', 'camera', type, (v) => setLocal(() => type = v)),
                      _typeChip('串口', 'serial', type, (v) => setLocal(() => type = v)),
                      _typeChip('网络流', 'stream', type, (v) => setLocal(() => type = v)),
                    ],
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: nameCtrl,
                    decoration: const InputDecoration(labelText: '显示名称', hintText: '例如 主摄像头'),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: targetCtrl,
                    decoration: InputDecoration(
                      labelText: '设备目标',
                      hintText: type == 'serial'
                          ? '例如 COM7'
                          : type == 'stream'
                              ? '例如 http://192.168.1.5:8080/video'
                              : '例如 0 或摄像头名称',
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    '添加后后端会自动探测一次，结果会显示在列表里。',
                    style: TextStyle(fontSize: 11.5, color: AppColors.subtle, height: 1.4),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: submitting ? null : () => Navigator.pop(context),
                child: const Text('取消'),
              ),
              FilledButton(
                onPressed: submitting ? null : submit,
                child: submitting
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('保存'),
              ),
            ],
          );
        },
      ),
    );

    targetCtrl.dispose();
    nameCtrl.dispose();
  }

  Widget _typeChip(String label, String value, String current, ValueChanged<String> onTap) {
    final active = current == value;
    return GestureDetector(
      onTap: () => onTap(value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: active ? AppColors.primary : const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: active ? AppColors.primary : AppColors.line),
        ),
        child: Text(
          label,
          style: TextStyle(fontSize: 12, color: active ? Colors.white : AppColors.subtle),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = widget.state.user?.isAdmin ?? false;

    return SafeArea(
      bottom: false,
      child: RefreshIndicator(
        color: AppColors.primary,
        onRefresh: () async {
          await Future.wait([_loadCamera(), _loadDevices()]);
          if (_videosExpanded) await _loadVideos();
        },
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          children: [
            Row(
              children: [
                const Text('设备管理', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AppColors.ink)),
                const Spacer(),
                IconButton(
                  tooltip: '刷新',
                  onPressed: () => Future.wait([_loadCamera(), _loadDevices()]),
                  icon: const Icon(Icons.refresh, color: AppColors.subtle),
                ),
              ],
            ),
            const SizedBox(height: 4),
            _cameraCard(isAdmin),
            const SizedBox(height: 18),
            Row(
              children: [
                const Expanded(child: SectionTitle(title: '我的设备')),
                if (isAdmin)
                  TextButton.icon(
                    onPressed: _showAddDevice,
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text('添加', style: TextStyle(fontSize: 12.5)),
                  ),
              ],
            ),
            if (_loadingDevices)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 20),
                child: Center(child: CircularProgressIndicator(color: AppColors.primary, strokeWidth: 2.2)),
              )
            else if (_devices.isEmpty)
              AppCard(
                child: const EmptyHint(text: '还没有保存设备，点右上角「添加」试试', icon: Icons.usb_off_outlined),
              )
            else
              ..._devices.map((device) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _deviceCard(device, isAdmin),
                  )),
            const SizedBox(height: 18),
            _videosCard(isAdmin),
          ],
        ),
      ),
    );
  }

  Widget _cameraCard(bool isAdmin) {
    final camera = _camera;
    final running = camera?.running ?? false;
    final error = camera?.error ?? '';

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: running ? const Color(0xFFECFDF5) : const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  Icons.videocam_outlined,
                  color: running ? AppColors.good : AppColors.subtle,
                  size: 22,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '后端摄像头采集',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: AppColors.ink),
                    ),
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            color: running ? AppColors.good : AppColors.subtle,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 5),
                        Text(
                          running ? '运行中 · ${camera?.fps ?? 8} fps' : '未运行',
                          style: const TextStyle(fontSize: 12, color: AppColors.subtle),
                        ),
                        if (running && (camera?.source.isNotEmpty ?? false)) ...[
                          const SizedBox(width: 6),
                          Flexible(
                            child: Text(
                              camera!.source,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ],
                ),
              ),
              if (isAdmin)
                FilledButton(
                  onPressed: _busy ? null : () => _toggleCamera(!running),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size(88, 38),
                    backgroundColor: running ? const Color(0xFFF1F5F9) : AppColors.primary,
                    foregroundColor: running ? AppColors.ink : Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                  ),
                  child: _busy
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Text(running ? '停止' : '启动', style: const TextStyle(fontSize: 13.5)),
                ),
            ],
          ),
          if (error.isNotEmpty) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: const Color(0xFFFEF2F2),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Row(
                children: [
                  const Icon(Icons.error_outline, color: AppColors.bad, size: 16),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(error, style: const TextStyle(fontSize: 11.5, color: AppColors.bad, height: 1.4)),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),
          Container(height: 1, color: AppColors.line),
          const SizedBox(height: 12),
          Row(
            children: [
              _statCell('累计帧', '${camera?.frames ?? 0}'),
              _statCell('识别命中', '${camera?.hits ?? 0}'),
              _statCell('已存图', '${camera?.snapshots ?? 0}'),
              _statCell('录像', '${camera?.videos ?? 0}'),
            ],
          ),
          const SizedBox(height: 8),
          if (isAdmin)
            Wrap(
              spacing: 8,
              runSpacing: 4,
              children: [
                _switchPill('识别', camera?.detect ?? true, 'detect'),
                _switchPill('存图', camera?.snapshot ?? true, 'snapshot'),
                _switchPill('录像', camera?.record ?? false, 'record'),
              ],
            )
          else
            const Text(
              '启动、停止与参数切换仅管理员可操作',
              style: TextStyle(fontSize: 11.5, color: AppColors.subtle),
            ),
        ],
      ),
    );
  }

  Widget _statCell(String label, String value) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(value, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: AppColors.ink)),
          const SizedBox(height: 2),
          Text(label, style: const TextStyle(fontSize: 11, color: AppColors.subtle)),
        ],
      ),
    );
  }

  Widget _switchPill(String label, bool value, String key) {
    return GestureDetector(
      onTap: _busy ? null : () => _toggleSwitch(key, !value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 6),
        decoration: BoxDecoration(
          color: value ? const Color(0xFFEFF6FF) : const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: value ? const Color(0xFFBFDBFE) : AppColors.line),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              value ? Icons.check_circle : Icons.radio_button_unchecked,
              size: 13,
              color: value ? AppColors.primary : AppColors.subtle,
            ),
            const SizedBox(width: 5),
            Text(
              label,
              style: TextStyle(
                fontSize: 11.5,
                color: value ? AppColors.primaryDark : AppColors.subtle,
                fontWeight: value ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _deviceCard(SavedDevice device, bool isAdmin) {
    final color = device.isOk ? AppColors.good : (device.isFail ? AppColors.bad : AppColors.subtle);
    final icon = device.devType == 'camera'
        ? Icons.photo_camera_outlined
        : (device.devType == 'serial' ? Icons.cable_outlined : Icons.stream);

    return AppCard(
      padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: const Color(0xFFF1F5F9),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(icon, size: 20, color: AppColors.ink),
              ),
              const SizedBox(width: 11),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            device.name.isEmpty ? device.target : device.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.ink),
                          ),
                        ),
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: const Color(0xFFF8FAFC),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(device.typeText, style: const TextStyle(fontSize: 10, color: AppColors.subtle)),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      device.target,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
                    ),
                  ],
                ),
              ),
              if (isAdmin)
                PopupMenuButton<String>(
                  icon: const Icon(Icons.more_horiz, color: AppColors.subtle, size: 20),
                  onSelected: (value) {
                    if (value == 'delete') _deleteDevice(device);
                    if (value == 'connect') _connectDevice(device);
                  },
                  itemBuilder: (context) => const [
                    PopupMenuItem(value: 'connect', child: Text('重新探测')),
                    PopupMenuItem(value: 'delete', child: Text('删除')),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Container(width: 7, height: 7, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  device.lastMessage.isEmpty
                      ? '尚未探测'
                      : device.lastMessage,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 11.5, color: color == AppColors.subtle ? AppColors.subtle : color, height: 1.35),
                ),
              ),
              if (isAdmin) ...[
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: _busy ? null : () => _connectDevice(device),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size(64, 32),
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    side: const BorderSide(color: AppColors.line),
                    foregroundColor: AppColors.primaryDark,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                  child: const Text('连接', style: TextStyle(fontSize: 12)),
                ),
              ],
            ],
          ),
          if (device.lastConnectTime.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              '最近探测 ${device.lastConnectTime}',
              style: const TextStyle(fontSize: 10.5, color: AppColors.subtle),
            ),
          ],
        ],
      ),
    );
  }

  Widget _videosCard(bool isAdmin) {
    return AppCard(
      padding: const EdgeInsets.fromLTRB(16, 8, 12, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () {
              setState(() => _videosExpanded = !_videosExpanded);
              if (_videosExpanded) _loadVideos();
            },
            child: Row(
              children: [
                const Expanded(child: SectionTitle(title: '命中录像', subtitle: '上传目录下已保存的视频')),
                Icon(
                  _videosExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                  color: AppColors.subtle,
                ),
              ],
            ),
          ),
          if (_videosExpanded) ...[
            if (_loadingVideos)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 14),
                child: Center(
                  child: SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary),
                  ),
                ),
              )
            else if (_videos.isEmpty)
              const EmptyHint(text: '还没有录像文件', icon: Icons.video_library_outlined)
            else
              ..._videos.map((video) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        const Icon(Icons.movie_outlined, size: 18, color: AppColors.subtle),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                video.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontSize: 12.5, color: AppColors.ink),
                              ),
                              Text(
                                '${video.sizeText} · ${video.createTime}',
                                style: const TextStyle(fontSize: 10.5, color: AppColors.subtle),
                              ),
                            ],
                          ),
                        ),
                        if (isAdmin)
                          IconButton(
                            onPressed: () async {
                              try {
                                await widget.state.api.deleteVideo(video.name);
                                if (!mounted) return;
                                toast(context, '已删除录像');
                                _loadVideos();
                              } on ApiException catch (e) {
                                if (mounted) toast(context, e.message);
                              }
                            },
                            icon: const Icon(Icons.delete_outline, size: 18, color: AppColors.subtle),
                          ),
                      ],
                    ),
                  )),
          ],
        ],
      ),
    );
  }
}
