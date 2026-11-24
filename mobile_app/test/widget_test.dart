import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:fruit_sorting_app/core/models.dart';
import 'package:fruit_sorting_app/core/theme.dart';

void main() {
  test('统计接口数据可以正确解析', () {
    final stats = StatsData.fromJson({
      'summary': {'today_total': 12, 'today_good': 9, 'today_bad': 3, 'good_rate': 75.0},
      'trend': {
        'labels': ['08:00', '09:00'],
        'total': [2, 10],
        'good': [1, 8],
        'rate': [50.0, 80.0],
      },
      'by_type': [
        {'name': '苹果', 'count': 8},
        {'name': '梨', 'count': 4},
      ],
    });

    expect(stats.todayTotal, 12);
    expect(stats.todayGood, 9);
    expect(stats.todayBad, 3);
    expect(stats.goodRate, 75.0);
    expect(stats.labels.length, 2);
    expect(stats.totalSeries[1], 10);
    expect(stats.byType.first.name, '苹果');
    expect(stats.maxSeries, 10);
  });

  testWidgets('卡片组件能正常渲染', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: const Scaffold(
          body: AppCard(child: Text('今日分拣')),
        ),
      ),
    );

    expect(find.text('今日分拣'), findsOneWidget);
  });
}
