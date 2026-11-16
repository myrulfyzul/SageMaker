import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sagemaker_flutter/core/network/app_failure.dart';
import 'package:sagemaker_flutter/features/admin/analytics/data/analytics_models.dart';
import 'package:sagemaker_flutter/features/admin/analytics/state/analytics_providers.dart';
import 'package:sagemaker_flutter/features/admin/analytics/ui/analytics_screen.dart';
import 'package:sagemaker_flutter/features/admin/dashboard/ui/dashboard_screen.dart';

class _FakeRepo implements AnalyticsRepository {
  _FakeRepo(this.dash, {this.report = const SalesReport()});
  DashboardData Function() dash;
  SalesReport report;
  int salesCalls = 0;

  @override
  Future<DashboardData> dashboard() async => dash();

  @override
  Future<SalesReport> sales(DateTime start, DateTime end) async {
    salesCalls++;
    return report;
  }
}

Widget _app(_FakeRepo repo, Widget child) => ProviderScope(
      overrides: [analyticsRepositoryProvider.overrideWithValue(repo)],
      child: MaterialApp(home: Scaffold(body: child)),
    );

void main() {
  group('validateRange', () {
    test('start after end is rejected', () {
      expect(validateRange(DateTime(2025, 2, 1), DateTime(2025, 1, 1)),
          isNotNull);
    });
    test('24 months ok, 25 months rejected', () {
      expect(validateRange(DateTime(2023, 1, 1), DateTime(2024, 12, 31)),
          isNull);
      expect(validateRange(DateTime(2023, 1, 1), DateTime(2025, 1, 1)),
          contains('24'));
    });
  });

  test('DashboardData parses backend shape', () {
    final d = DashboardData.fromJson({
      'kpis': {'totalRevenueSen': 4600, 'orderCount': 2, 'aovSen': 2300},
      'salesByMonth': [
        {'month': '2025-05', 'revenueSen': 4600, 'orderCount': 2}
      ],
      'ordersByStatus': {'placed': 2},
      'bestSellers': [
        {'productId': 'p1', 'name': 'A', 'units': 3}
      ],
      'inventoryByCategory': [
        {'category': 'Toys', 'units': 5}
      ],
    });
    expect(d.kpis.totalRevenueSen, 4600);
    expect(d.salesEmpty, isFalse);
    expect(d.hasData, isTrue);
  });

  testWidgets('dashboard zero state shows RM 0.00 and chart empty states',
      (tester) async {
    final repo = _FakeRepo(() => const DashboardData());
    tester.view.physicalSize = const Size(800, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_app(repo, const DashboardScreen()));
    await tester.pumpAndSettle();
    expect(find.text('RM 0.00'), findsNWidgets(2));
    expect(find.text('No data yet.'), findsNWidgets(4));
    expect(find.text('Demo data'), findsNothing);
  });

  testWidgets('dashboard shows data without a demo label and chart semantics',
      (tester) async {
    final handle = tester.ensureSemantics();
    final repo = _FakeRepo(() => DashboardData(
          kpis: const DashboardKpis(totalRevenueSen: 4600, orderCount: 2),
          salesByMonth: const [MonthSales('2025-05', 4600, 2)],
          ordersByStatus: const {'placed': 2},
          bestSellers: const [ProductUnits('p1', 'Alpha', 3)],
          inventoryByCategory: const [CategoryUnits('Toys', 5)],
        ));
    tester.view.physicalSize = const Size(800, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_app(repo, const DashboardScreen()));
    await tester.pumpAndSettle();
    expect(find.text('RM 46.00'), findsOneWidget);
    expect(find.text('Demo data'), findsNothing);
    expect(find.bySemanticsLabel(RegExp('Sales by month.*RM 46.00')),
        findsOneWidget);
    handle.dispose();
  });

  testWidgets('dashboard keeps values and shows retry when refresh fails',
      (tester) async {
    var fail = false;
    final repo = _FakeRepo(() {
      if (fail) throw const NetworkFailure();
      return const DashboardData(kpis: DashboardKpis(orderCount: 7));
    });
    tester.view.physicalSize = const Size(800, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_app(repo, const DashboardScreen()));
    await tester.pumpAndSettle();
    fail = true;
    final container = ProviderScope.containerOf(
        tester.element(find.byType(DashboardScreen)));
    await container.read(dashboardProvider.notifier).refresh();
    await tester.pumpAndSettle();
    expect(find.text('7'), findsOneWidget);
    expect(find.text('Could not load the dashboard.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('analytics loads default range and reports invalid range',
      (tester) async {
    final repo = _FakeRepo(() => const DashboardData(),
        report: const SalesReport(
            totalRevenueSen: 1000,
            orderCount: 1,
            aovSen: 1000,
            monthly: [MonthSales('2025-05', 1000, 1)]));
    await tester.pumpWidget(_app(repo, const AnalyticsScreen()));
    await tester.pumpAndSettle();
    expect(repo.salesCalls, 1);
    expect(find.text('RM 10.00'), findsNWidgets(2));

    final container = ProviderScope.containerOf(
        tester.element(find.byType(AnalyticsScreen)));
    final s = container.read(analyticsProvider);
    await container
        .read(analyticsProvider.notifier)
        .setRange(end: s.start.subtract(const Duration(days: 1)));
    await tester.pumpAndSettle();
    expect(find.text('The start date must not be after the end date'),
        findsOneWidget);
    expect(repo.salesCalls, 1);
    expect(find.text('RM 10.00'), findsNWidgets(2));
  });
}

