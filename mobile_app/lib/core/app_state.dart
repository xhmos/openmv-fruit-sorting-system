import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api_client.dart';
import 'models.dart';
import 'realtime_service.dart';

/// 全局状态：服务器地址、登录令牌、当前用户、实时通道
class AppState extends ChangeNotifier {
  /// 首次打开预填的地址：后端跑在保存这个工程的那台电脑上（WLAN 网段）
  static const defaultBaseUrl = 'http://10.153.180.220:5000';

  static const _keyBaseUrl = 'app.base_url';
  static const _keyToken = 'app.token';
  static const _keyUser = 'app.user';

  late ApiClient api;
  final RealtimeService realtime = RealtimeService();

  String baseUrl = defaultBaseUrl;
  String? token;
  UserInfo? user;

  /// 令牌过期时通知界面回登录页
  void Function()? onSessionEnd;

  bool get hasSession => (token ?? '').isNotEmpty;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = (prefs.getString(_keyBaseUrl) ?? '').trim();
    if (baseUrl.isEmpty) baseUrl = defaultBaseUrl;
    token = prefs.getString(_keyToken);
    user = _decodeUser(prefs.getString(_keyUser));

    api = ApiClient(baseUrl: baseUrl, token: token, onUnauthorized: _handleUnauthorized);
    notifyListeners();

    if (hasSession) {
      try {
        user = await api.me();
        await _saveUser(user);
        realtime.connect(baseUrl, token!);
      } on ApiException catch (e) {
        // 网络不通时保留本地缓存用户先进入界面；令牌失效则回登录页
        if (e.statusCode == 401) {
          await clearSession();
        }
      } catch (_) {}
      notifyListeners();
    }
  }

  UserInfo? _decodeUser(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    try {
      final json = jsonDecode(raw);
      if (json is Map) return UserInfo.fromJson(Map<String, dynamic>.from(json));
    } catch (_) {}
    return null;
  }

  Future<void> _saveUser(UserInfo? value) async {
    final prefs = await SharedPreferences.getInstance();
    if (value == null) {
      await prefs.remove(_keyUser);
    } else {
      await prefs.setString(_keyUser, jsonEncode(value.toJson()));
    }
  }

  Future<void> setBaseUrl(String value) async {
    var url = value.trim();
    if (url.isEmpty) return;
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'http://$url';
    }
    url = url.replaceAll(RegExp(r'/+$'), '');

    final changed = url != baseUrl;
    baseUrl = url;
    api.baseUrl = url;

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, url);

    if (changed && hasSession) {
      await clearSession(silent: true);
    }
    notifyListeners();
  }

  Future<void> login(String username, String password) async {
    final data = await api.login(username, password);
    final newToken = '${data['token'] ?? ''}';
    if (newToken.isEmpty) throw ApiException('登录失败：服务器未返回令牌');

    token = newToken;
    api.token = newToken;
    user = UserInfo.fromJson(asMap(data['user']));

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyToken, newToken);
    await _saveUser(user);

    realtime.connect(baseUrl, newToken);
    notifyListeners();
  }

  Future<void> updateUser(UserInfo value) async {
    user = value;
    await _saveUser(value);
    notifyListeners();
  }

  Future<void> clearSession({bool silent = false}) async {
    token = null;
    user = null;
    api.token = null;
    realtime.disconnect();

    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyToken);
    await prefs.remove(_keyUser);

    notifyListeners();
    if (!silent) onSessionEnd?.call();
  }

  Future<void> logout() async {
    await api.logout();
    await clearSession();
  }

  void _handleUnauthorized() {
    if (!hasSession) return;
    // 立即清本地状态，界面会切回登录页
    clearSession();
  }

  @override
  void dispose() {
    realtime.dispose();
    super.dispose();
  }
}
