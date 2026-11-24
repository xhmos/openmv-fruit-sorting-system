import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

/// 解析 MJPEG（multipart/x-mixed-replace）并按帧显示。
/// 后端 /api/device/stream 与 /api/device/live 都是这个格式。
class LiveFrameView extends StatefulWidget {
  const LiveFrameView({
    super.key,
    required this.url,
    this.enabled = true,
    this.height,
    this.emptyText = '暂无画面',
  });

  final String url;
  final bool enabled;
  final double? height;
  final String emptyText;

  @override
  State<LiveFrameView> createState() => _LiveFrameViewState();
}

class _LiveFrameViewState extends State<LiveFrameView> {
  _MjpegStreamer? _streamer;
  Timer? _retryTimer;
  Uint8List? _frame;
  String? _error;
  int _lastFrameAt = 0;

  @override
  void initState() {
    super.initState();
    if (widget.enabled) _start();
  }

  @override
  void didUpdateWidget(covariant LiveFrameView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url || oldWidget.enabled != widget.enabled) {
      if (widget.enabled) {
        _start();
      } else {
        _stop();
      }
    }
  }

  void _start() {
    _stop();
    setState(() {
      _frame = null;
      _error = null;
    });
    _streamer = _MjpegStreamer(
      onFrame: (bytes) {
        if (!mounted) return;
        final now = DateTime.now().millisecondsSinceEpoch;
        // 约 10fps 上限，避免手机解码压力过大
        if (_frame != null && now - _lastFrameAt < 90) return;
        _lastFrameAt = now;
        setState(() {
          _frame = bytes;
          _error = null;
        });
      },
      onError: (message) {
        if (!mounted) return;
        setState(() => _error = message);
        _scheduleRetry();
      },
    )..start(widget.url);
  }

  void _scheduleRetry() {
    _retryTimer?.cancel();
    _retryTimer = Timer(const Duration(seconds: 3), () {
      if (!mounted || !widget.enabled) return;
      _start();
    });
  }

  void _stop() {
    _retryTimer?.cancel();
    _retryTimer = null;
    _streamer?.close();
    _streamer = null;
  }

  @override
  void dispose() {
    _stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final frame = _frame;

    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        height: widget.height,
        width: double.infinity,
        color: const Color(0xFF0B1220),
        child: Stack(
          fit: StackFit.expand,
          children: [
            if (frame != null)
              Image.memory(frame, gaplessPlayback: true, fit: BoxFit.cover)
            else
              Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (_error == null)
                      const SizedBox(
                        width: 26,
                        height: 26,
                        child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white70),
                      )
                    else
                      const Icon(Icons.videocam_off_outlined, color: Colors.white54, size: 34),
                    const SizedBox(height: 10),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: Text(
                        _error ??
                            (widget.enabled ? '正在连接实时画面…' : widget.emptyText),
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: Colors.white70, fontSize: 12.5, height: 1.4),
                      ),
                    ),
                  ],
                ),
              ),
            if (frame != null)
              Positioned(
                left: 10,
                top: 10,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.45),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 7,
                        height: 7,
                        decoration: const BoxDecoration(color: Color(0xFF22C55E), shape: BoxShape.circle),
                      ),
                      const SizedBox(width: 6),
                      const Text('实时', style: TextStyle(color: Colors.white, fontSize: 11.5)),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _MjpegStreamer {
  _MjpegStreamer({required this.onFrame, required this.onError});

  final void Function(Uint8List bytes) onFrame;
  final void Function(String message) onError;

  http.Client? _client;
  StreamSubscription<List<int>>? _subscription;
  final List<int> _buffer = <int>[];
  bool _closed = false;

  void start(String url) {
    _closed = false;
    final client = http.Client();
    _client = client;

    final request = http.Request('GET', Uri.parse(url));
    client
        .send(request)
        .timeout(const Duration(seconds: 8))
        .then((response) {
          if (_closed) return;
          if (response.statusCode != 200) {
            onError('取流失败（HTTP ${response.statusCode}）');
            return;
          }
          _subscription = response.stream.listen(
            _onChunk,
            onError: (Object _) {
              if (!_closed) onError('画面连接中断');
            },
            onDone: () {
              if (!_closed) onError('画面连接已断开');
            },
            cancelOnError: true,
          );
        })
        .catchError((Object _) {
          if (!_closed) onError('无法连接实时画面');
        });
  }

  void _onChunk(List<int> chunk) {
    if (_closed) return;
    _buffer.addAll(chunk);

    // 防止数据异常时缓冲区无限增长
    if (_buffer.length > 6 * 1024 * 1024) {
      _buffer.removeRange(0, _buffer.length - 1024 * 1024);
    }

    while (true) {
      final start = _indexOfMarker(0xD8, from: 0);
      if (start < 0) {
        if (_buffer.length > 2) _buffer.removeRange(0, _buffer.length - 2);
        return;
      }
      final end = _indexOfMarker(0xD9, from: start + 2);
      if (end < 0) {
        if (start > 0) _buffer.removeRange(0, start);
        return;
      }
      final bytes = Uint8List.fromList(_buffer.sublist(start, end + 2));
      _buffer.removeRange(0, end + 2);
      if (bytes.length > 4) onFrame(bytes);
    }
  }

  int _indexOfMarker(int marker, {required int from}) {
    for (var i = from; i < _buffer.length - 1; i++) {
      if (_buffer[i] == 0xFF && _buffer[i + 1] == marker) return i;
    }
    return -1;
  }

  void close() {
    _closed = true;
    _subscription?.cancel();
    _subscription = null;
    _client?.close();
    _client = null;
    _buffer.clear();
  }
}
