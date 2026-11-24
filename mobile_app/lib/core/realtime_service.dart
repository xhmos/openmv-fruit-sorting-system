import 'dart:async';

import 'package:socket_io_client/socket_io_client.dart' as io;

/// SocketIO 实时通道：新分拣记录（new_record）、新画面（live_frame）
class RealtimeService {
  io.Socket? _socket;

  final _records = StreamController<Map<String, dynamic>>.broadcast();
  final _frames = StreamController<void>.broadcast();
  final _state = StreamController<bool>.broadcast();

  Stream<Map<String, dynamic>> get records => _records.stream;
  Stream<void> get frames => _frames.stream;
  Stream<bool> get connectionState => _state.stream;

  bool get connected => _socket?.connected == true;

  void connect(String baseUrl, String token) {
    disconnect();
    final url = baseUrl.trim().replaceAll(RegExp(r'/+$'), '');
    try {
      final socket = io.io(url, <String, dynamic>{
        'transports': ['websocket', 'polling'],
        'auth': {'token': token},
        'autoConnect': true,
        'reconnection': true,
        'reconnectionDelay': 2000,
      });
      _socket = socket;

      socket.onConnect((_) => _state.add(true));
      socket.onDisconnect((_) => _state.add(false));
      socket.onConnectError((_) => _state.add(false));
      socket.onError((_) => _state.add(false));

      socket.on('new_record', (data) {
        if (data is Map) {
          _records.add(Map<String, dynamic>.from(data));
        }
      });
      socket.on('live_frame', (_) => _frames.add(null));
    } catch (_) {
      _state.add(false);
    }
  }

  void disconnect() {
    final socket = _socket;
    _socket = null;
    if (socket == null) return;
    try {
      socket.dispose();
    } catch (_) {}
  }

  void dispose() {
    disconnect();
    _records.close();
    _frames.close();
    _state.close();
  }
}
