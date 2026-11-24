import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

/// 后端返回的错误（msg 直接拿去给用户看）
class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.baseUrl, this.token, this.onUnauthorized});

  String baseUrl;
  String? token;
  void Function()? onUnauthorized;

  final http.Client _http = http.Client();

  /// 把后端返回的相对路径（如 /uploads/xxx.jpg）拼成完整地址
  String absolute(String path) {
    if (path.isEmpty) return '';
    if (path.startsWith('http://') || path.startsWith('https://')) return path;
    final root = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    return path.startsWith('/') ? '$root$path' : '$root/$path';
  }

  Uri _uri(String path, [Map<String, dynamic>? query]) {
    final root = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    final params = <String, String>{};
    query?.forEach((key, value) {
      if (value == null) return;
      final text = '$value'.trim();
      if (text.isEmpty) return;
      params[key] = text;
    });
    final uri = Uri.parse('$root$path');
    return params.isEmpty ? uri : uri.replace(queryParameters: params);
  }

  Map<String, String> _headers({bool json = false}) {
    return {
      'Accept': 'application/json',
      if (json) 'Content-Type': 'application/json; charset=utf-8',
      if (token != null && token!.isNotEmpty) 'Authorization': 'Bearer $token',
    };
  }

  Future<dynamic> _request(
    String method,
    String path, {
    Map<String, dynamic>? query,
    Object? body,
    Duration timeout = const Duration(seconds: 20),
  }) async {
    final uri = _uri(path, query);
    http.Response response;

    try {
      switch (method) {
        case 'GET':
          response = await _http.get(uri, headers: _headers()).timeout(timeout);
          break;
        case 'POST':
          response = await _http
              .post(uri, headers: _headers(json: true), body: body == null ? '{}' : jsonEncode(body))
              .timeout(timeout);
          break;
        case 'PUT':
          response = await _http
              .put(uri, headers: _headers(json: true), body: body == null ? '{}' : jsonEncode(body))
              .timeout(timeout);
          break;
        case 'PATCH':
          response = await _http
              .patch(uri, headers: _headers(json: true), body: body == null ? '{}' : jsonEncode(body))
              .timeout(timeout);
          break;
        case 'DELETE':
          response = await _http.delete(uri, headers: _headers()).timeout(timeout);
          break;
        default:
          throw ApiException('不支持的请求方式：$method');
      }
    } on TimeoutException {
      throw ApiException('请求超时，请检查手机网络或电脑端后端是否在运行');
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ApiException('无法连接服务器，请确认手机与电脑在同一 WiFi、地址填写正确');
    }

    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    final status = response.statusCode;
    Map<String, dynamic>? payload;
    try {
      final decoded = jsonDecode(utf8.decode(response.bodyBytes));
      if (decoded is Map) payload = Map<String, dynamic>.from(decoded);
    } catch (_) {
      payload = null;
    }

    final msg = '${payload?['msg'] ?? ''}';

    if (status == 401) {
      onUnauthorized?.call();
      throw ApiException(msg.isEmpty ? '登录已过期，请重新登录' : msg, statusCode: status);
    }

    if (payload == null) {
      if (status >= 400) throw ApiException('服务器返回异常（HTTP $status）', statusCode: status);
      throw ApiException('服务器响应格式异常');
    }

    final code = payload['code'];
    if (code is num && code != 0) {
      throw ApiException(msg.isEmpty ? '操作失败' : msg, statusCode: status);
    }
    if (status >= 400) {
      throw ApiException(msg.isEmpty ? '请求失败（HTTP $status）' : msg, statusCode: status);
    }
    return payload['data'];
  }

  // ------------------------------------------------ 认证
  Future<String> checkHealth() async {
    final data = await _request('GET', '/api/health', timeout: const Duration(seconds: 10));
    return '${asMap(data)['service'] ?? 'ok'}';
  }

  Future<Map<String, dynamic>> login(String username, String password) async {
    final data = await _request(
      'POST',
      '/api/auth/login',
      body: {'username': username.trim(), 'password': password},
      timeout: const Duration(seconds: 15),
    );
    return asMap(data);
  }

  Future<UserInfo> me() async {
    final data = await _request('GET', '/api/auth/me');
    return UserInfo.fromJson(asMap(data));
  }

  Future<void> logout() async {
    try {
      await _request('POST', '/api/auth/logout');
    } catch (_) {
      // 退出失败不影响本地清理
    }
  }

  Future<UserInfo> uploadAvatar(List<int> bytes, String filename) async {
    final uri = _uri('/api/auth/avatar');
    final request = http.MultipartRequest('POST', uri);
    request.headers.addAll(_headers());
    request.files.add(http.MultipartFile.fromBytes('file', bytes, filename: filename));

    http.Response response;
    try {
      final streamed = await _http.send(request).timeout(const Duration(seconds: 30));
      response = await http.Response.fromStream(streamed);
    } on TimeoutException {
      throw ApiException('头像上传超时，请稍后重试');
    } catch (_) {
      throw ApiException('无法连接服务器，头像上传失败');
    }
    final data = _decode(response);
    return UserInfo.fromJson(asMap(data));
  }

  Future<UserInfo> resetAvatar() async {
    final data = await _request('DELETE', '/api/auth/avatar');
    return UserInfo.fromJson(asMap(data));
  }

  // ------------------------------------------------ 分拣记录
  Future<Map<String, dynamic>> records({
    int page = 1,
    int pageSize = 10,
    String fruitType = '',
    String result = '',
    String start = '',
    String end = '',
  }) async {
    final data = await _request('GET', '/api/record/list', query: {
      'page': page,
      'page_size': pageSize,
      'fruit_type': fruitType,
      'result': result,
      'start': start,
      'end': end,
    });
    return asMap(data);
  }

  Future<StatsData> stats({int days = 1}) async {
    final data = await _request('GET', '/api/record/stats', query: {'days': days});
    return StatsData.fromJson(asMap(data));
  }

  Future<void> deleteRecord(int id) => _request('DELETE', '/api/record/$id');

  Future<SortRecord?> latestRecord() async {
    final data = await _request('GET', '/api/device/latest');
    final map = asMap(data);
    if (map.isEmpty) return null;
    return SortRecord.fromJson(map);
  }

  // ------------------------------------------------ 设备 / 摄像头
  Future<CameraStatus> cameraStatus() async {
    final data = await _request('GET', '/api/device/camera/status');
    return CameraStatus(asMap(data));
  }

  Future<CameraStatus> startCamera({
    String source = '',
    int fps = 8,
    bool detect = true,
    bool snapshot = true,
    bool record = false,
    int minArea = 300,
    double cooldown = 3,
    double minConfidence = 0.65,
  }) async {
    final data = await _request(
      'POST',
      '/api/device/camera/start',
      body: {
        'source': source,
        'fps': fps,
        'detect': detect,
        'snapshot': snapshot,
        'record': record,
        'min_area': minArea,
        'cooldown': cooldown,
        'min_confidence': minConfidence,
      },
      timeout: const Duration(seconds: 30),
    );
    return CameraStatus(asMap(data));
  }

  Future<CameraStatus> stopCamera() async {
    final data = await _request(
      'POST',
      '/api/device/camera/stop',
      body: const {},
      timeout: const Duration(seconds: 20),
    );
    return CameraStatus(asMap(data));
  }

  Future<CameraStatus> updateCameraConfig(Map<String, dynamic> config) async {
    final data = await _request('PATCH', '/api/device/camera/config', body: config);
    return CameraStatus(asMap(data));
  }

  Future<List<SavedDevice>> savedDevices() async {
    final data = await _request('GET', '/api/system/saved');
    return asMapList(asMap(data)['items']).map(SavedDevice.fromJson).toList();
  }

  Future<Map<String, dynamic>> addDevice({
    required String devType,
    required String target,
    required String name,
    String note = '',
  }) async {
    final data = await _request(
      'POST',
      '/api/system/saved',
      body: {'dev_type': devType, 'target': target, 'name': name, 'note': note, 'auto_connect': true},
      timeout: const Duration(seconds: 30),
    );
    return asMap(data);
  }

  Future<Map<String, dynamic>> connectDevice(int id) async {
    final data = await _request(
      'POST',
      '/api/system/saved/$id/connect',
      body: const {},
      timeout: const Duration(seconds: 30),
    );
    return asMap(data);
  }

  Future<void> deleteDevice(int id) => _request('DELETE', '/api/system/saved/$id');

  Future<List<VideoItem>> videos() async {
    final data = await _request('GET', '/api/device/videos');
    return asMapList(asMap(data)['items']).map(VideoItem.fromJson).toList();
  }

  Future<void> deleteVideo(String name) =>
      _request('DELETE', '/api/device/videos/${Uri.encodeComponent(name)}');

  // ------------------------------------------------ 识别参数
  Future<List<SettingItem>> settings() async {
    final data = await _request('GET', '/api/setting/list');
    return asMapList(asMap(data)['items']).map(SettingItem.fromJson).toList();
  }

  Future<void> updateSettings(Map<String, int> settings) =>
      _request('PUT', '/api/setting/update', body: {'settings': settings});
}
