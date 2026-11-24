import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/theme.dart';
import '../widgets/server_settings_sheet.dart';
import 'params_page.dart';

class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key, required this.state});

  final AppState state;

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  bool _uploading = false;

  AppState get state => widget.state;

  String get _avatarUrl {
    final avatar = state.user?.avatar ?? '';
    if (avatar.isEmpty) return '';
    return state.api.absolute('/uploads/$avatar');
  }

  Future<void> _pickAvatar() async {
    final action = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(22)),
        ),
        child: SafeArea(
          top: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 6),
              const Text('账号头像', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              ListTile(
                leading: const Icon(Icons.photo_library_outlined, color: AppColors.primary),
                title: const Text('从相册选择'),
                onTap: () => Navigator.pop(context, 'pick'),
              ),
              if ((state.user?.avatar ?? '').isNotEmpty)
                ListTile(
                  leading: const Icon(Icons.person_remove_outlined, color: AppColors.bad),
                  title: const Text('恢复默认头像', style: TextStyle(color: AppColors.bad)),
                  onTap: () => Navigator.pop(context, 'reset'),
                ),
              const SizedBox(height: 6),
            ],
          ),
        ),
      ),
    );

    if (action == 'reset') {
      await _resetAvatar();
    } else if (action == 'pick') {
      await _uploadAvatar();
    }
  }

  Future<void> _uploadAvatar() async {
    if (_uploading) return;
    try {
      final picker = ImagePicker();
      final picked = await picker.pickImage(source: ImageSource.gallery, maxWidth: 900, imageQuality: 85);
      if (picked == null) return;

      setState(() => _uploading = true);
      final bytes = await picked.readAsBytes();
      final filename = picked.name.toLowerCase().endsWith('.png') ? picked.name : 'avatar.jpg';
      final user = await state.api.uploadAvatar(bytes, filename);
      await state.updateUser(user);
      if (mounted) toast(context, '头像已更新');
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    } catch (_) {
      if (mounted) toast(context, '头像处理失败，请换一张图片试试');
    } finally {
      if (mounted) setState(() => _uploading = false);
    }
  }

  Future<void> _resetAvatar() async {
    try {
      final user = await state.api.resetAvatar();
      await state.updateUser(user);
      if (mounted) toast(context, '已恢复默认头像');
    } on ApiException catch (e) {
      if (mounted) toast(context, e.message);
    }
  }

  Future<void> _changeServer() async {
    final url = await showServerSettingsSheet(context, current: state.baseUrl);
    if (url == null) return;
    if (url == state.baseUrl) return;
    await state.setBaseUrl(url);
    if (mounted) toast(context, '服务器地址已修改，请重新登录');
  }

  Future<void> _logout() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('退出登录'),
        content: const Text('退出后需要重新输入账号密码。'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('取消')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('退出')),
        ],
      ),
    );
    if (ok != true) return;
    await state.logout();
  }

  @override
  Widget build(BuildContext context) {
    final user = state.user;
    final isAdmin = user?.isAdmin ?? false;

    return SafeArea(
      bottom: false,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(
              gradient: AppColors.headerGradient,
              borderRadius: BorderRadius.circular(22),
              boxShadow: [
                BoxShadow(
                  color: AppColors.primaryDark.withValues(alpha: 0.22),
                  blurRadius: 22,
                  offset: const Offset(0, 10),
                ),
              ],
            ),
            child: Row(
              children: [
                InkWell(
                  onTap: _uploading ? null : _pickAvatar,
                  borderRadius: BorderRadius.circular(34),
                  child: Stack(
                    children: [
                      Container(
                        width: 66,
                        height: 66,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.22),
                          shape: BoxShape.circle,
                          border: Border.all(color: Colors.white.withValues(alpha: 0.5), width: 1.5),
                        ),
                        clipBehavior: Clip.antiAlias,
                        child: _avatarUrl.isEmpty
                            ? Center(
                                child: Text(
                                  (user?.username ?? '?').substring(0, 1).toUpperCase(),
                                  style: const TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w700),
                                ),
                              )
                            : Image.network(
                                _avatarUrl,
                                fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Center(
                                  child: Text(
                                    (user?.username ?? '?').substring(0, 1).toUpperCase(),
                                    style: const TextStyle(color: Colors.white, fontSize: 26, fontWeight: FontWeight.w700),
                                  ),
                                ),
                              ),
                      ),
                      Positioned(
                        right: 0,
                        bottom: 0,
                        child: Container(
                          padding: const EdgeInsets.all(4),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            shape: BoxShape.circle,
                          ),
                          child: _uploading
                              ? const SizedBox(
                                  width: 12,
                                  height: 12,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: AppColors.primary),
                                )
                              : const Icon(Icons.camera_alt, size: 12, color: AppColors.primary),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        user?.username ?? '未登录',
                        style: const TextStyle(color: Colors.white, fontSize: 21, fontWeight: FontWeight.w700),
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Text(
                              user?.roleText ?? '——',
                              style: const TextStyle(color: Colors.white, fontSize: 11.5, fontWeight: FontWeight.w500),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            (user?.isActive ?? false) ? '账号正常' : '账号已禁用',
                            style: TextStyle(color: Colors.white.withValues(alpha: 0.8), fontSize: 11.5),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Text(
                        '注册于 ${user?.createTime ?? '——'}',
                        style: TextStyle(color: Colors.white.withValues(alpha: 0.75), fontSize: 11),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          AppCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                _tile(
                  icon: Icons.dns_outlined,
                  title: '服务器地址',
                  subtitle: state.baseUrl,
                  onTap: _changeServer,
                ),
                if (isAdmin) ...[
                  const Divider(height: 1),
                  _tile(
                    icon: Icons.tune,
                    title: '识别参数',
                    subtitle: '色相 / 饱和度 / 亮度 / 最小面积',
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => ParamsPage(state: state)),
                      );
                    },
                  ),
                ],
                const Divider(height: 1),
                _tile(
                  icon: Icons.sync_outlined,
                  title: '账号信息刷新',
                  subtitle: '从后端重新读取角色与权限',
                  onTap: () async {
                    try {
                      final me = await state.api.me();
                      await state.updateUser(me);
                      if (mounted) toast(context, '账号信息已刷新');
                    } on ApiException catch (e) {
                      if (mounted) toast(context, e.message);
                    }
                  },
                ),
                const Divider(height: 1),
                _tile(
                  icon: Icons.info_outline,
                  title: '关于',
                  subtitle: '果实分拣系统手机端 v1.0.0',
                  onTap: () => showAboutDialog(
                    context: context,
                    applicationName: '果实分拣系统 · 手机端',
                    applicationVersion: '1.0.0',
                    applicationIcon: const Icon(Icons.eco_rounded, color: AppColors.primary, size: 36),
                    children: const [
                      Text(
                        '基于 OpenMV 的果实智能分拣系统移动端，与网页端共用同一套 Flask 后端。\n\n支持今日汇总、趋势曲线、实时画面、分拣记录、摄像头采集控制与识别参数配置。',
                        style: TextStyle(fontSize: 12.5, height: 1.6),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          OutlinedButton(
            onPressed: _logout,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.bad,
              side: const BorderSide(color: Color(0xFFFCA5A5)),
              minimumSize: const Size(0, 50),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              backgroundColor: Colors.white,
            ),
            child: const Text('退出登录', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          ),
          const SizedBox(height: 16),
          const Center(
            child: Text(
              '连接地址保存在本机，换网络后可在「服务器地址」里修改',
              style: TextStyle(fontSize: 11, color: AppColors.subtle),
            ),
          ),
        ],
      ),
    );
  }

  Widget _tile({
    required IconData icon,
    required String title,
    String? subtitle,
    required VoidCallback onTap,
  }) {
    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Container(
        width: 38,
        height: 38,
        decoration: BoxDecoration(
          color: const Color(0xFFEFF6FF),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: AppColors.primaryDark, size: 20),
      ),
      title: Text(title, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: AppColors.ink)),
      subtitle: subtitle == null
          ? null
          : Text(
              subtitle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 11.5, color: AppColors.subtle),
            ),
      trailing: const Icon(Icons.chevron_right, color: AppColors.subtle, size: 18),
    );
  }
}
