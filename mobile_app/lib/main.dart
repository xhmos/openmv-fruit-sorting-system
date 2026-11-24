import 'package:flutter/material.dart';

import 'core/app_state.dart';
import 'core/theme.dart';
import 'pages/home_page.dart';
import 'pages/login_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final state = AppState();
  await state.init();
  runApp(FruitApp(state: state));
}

class FruitApp extends StatefulWidget {
  const FruitApp({super.key, required this.state, this.initialTab = 0});

  final AppState state;
  final int initialTab;

  @override
  State<FruitApp> createState() => _FruitAppState();
}

class _FruitAppState extends State<FruitApp> {
  final GlobalKey<NavigatorState> _navigatorKey = GlobalKey<NavigatorState>();

  @override
  void initState() {
    super.initState();
    widget.state.onSessionEnd = () {
      _navigatorKey.currentState?.popUntil((route) => route.isFirst);
    };
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _navigatorKey,
      title: '果实分拣',
      debugShowCheckedModeBanner: false,
      theme: buildTheme(),
      home: AuthGate(state: widget.state, initialTab: widget.initialTab),
    );
  }
}

/// 根据登录状态切换「登录页 / 主页」
class AuthGate extends StatelessWidget {
  const AuthGate({super.key, required this.state, this.initialTab = 0});

  final AppState state;
  final int initialTab;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: state,
      builder: (context, _) {
        return state.hasSession
            ? HomePage(state: state, initialIndex: initialTab)
            : LoginPage(state: state);
      },
    );
  }
}
