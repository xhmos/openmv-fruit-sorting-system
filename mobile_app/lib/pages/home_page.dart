import 'package:flutter/material.dart';

import '../core/app_state.dart';
import 'dashboard_page.dart';
import 'devices_page.dart';
import 'profile_page.dart';
import 'records_page.dart';

class HomePage extends StatefulWidget {
  const HomePage({super.key, required this.state, this.initialIndex = 0});

  final AppState state;
  final int initialIndex;

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final ValueNotifier<int> _activeTab = ValueNotifier<int>(0);
  int _index = 0;
  late final List<Widget> _pages;

  @override
  void initState() {
    super.initState();
    _index = widget.initialIndex.clamp(0, 3);
    _activeTab.value = _index;
    _pages = [
      DashboardPage(state: widget.state, activeTab: _activeTab),
      RecordsPage(state: widget.state),
      DevicesPage(state: widget.state),
      ProfilePage(state: widget.state),
    ];
  }

  @override
  void dispose() {
    _activeTab.dispose();
    super.dispose();
  }

  void _select(int index) {
    if (_index == index) return;
    setState(() => _index = index);
    _activeTab.value = index;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(index: _index, children: _pages),
      bottomNavigationBar: NavigationBarTheme(
        data: NavigationBarThemeData(
          backgroundColor: Colors.white,
          indicatorColor: const Color(0xFFDBEAFE),
          labelTextStyle: WidgetStateProperty.resolveWith((states) {
            final selected = states.contains(WidgetState.selected);
            return TextStyle(
              fontSize: 12,
              fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
              color: selected ? const Color(0xFF1D4ED8) : const Color(0xFF64748B),
            );
          }),
          iconTheme: WidgetStateProperty.resolveWith((states) {
            final selected = states.contains(WidgetState.selected);
            return IconThemeData(
              size: 23,
              color: selected ? const Color(0xFF1D4ED8) : const Color(0xFF64748B),
            );
          }),
        ),
        child: NavigationBar(
          height: 64,
          selectedIndex: _index,
          onDestinationSelected: _select,
          destinations: const [
            NavigationDestination(icon: Icon(Icons.space_dashboard_outlined), selectedIcon: Icon(Icons.space_dashboard), label: '看板'),
            NavigationDestination(icon: Icon(Icons.list_alt_outlined), selectedIcon: Icon(Icons.list_alt), label: '记录'),
            NavigationDestination(icon: Icon(Icons.precision_manufacturing_outlined), selectedIcon: Icon(Icons.precision_manufacturing), label: '设备'),
            NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: '我的'),
          ],
        ),
      ),
    );
  }
}
