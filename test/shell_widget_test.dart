import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:sagemaker_flutter/app/router.dart';
import 'package:sagemaker_flutter/app/shells/customer_shell.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/features/admin/analytics/data/analytics_models.dart';
import 'package:sagemaker_flutter/features/admin/analytics/state/analytics_providers.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/cart/state/cart_provider.dart';

const _seller =
    AuthUser(id: 4, name: 'S', email: 's@x.my', role: AppRole.seller);

class _EmptyCart extends CartNotifier {
  @override
  Future<CartState> build() async => const CartState();
}

class _EmptyAnalytics implements AnalyticsRepository {
  @override
  Future<DashboardData> dashboard() async => const DashboardData();
  @override
  Future<SalesReport> sales(DateTime start, DateTime end) async =>
      const SalesReport();
}

class _FakeSession extends SessionNotifier {
  _FakeSession(this.initial);
  final SessionState initial;

  @override
  SessionState build() => initial;
}

Future<(GoRouter, ProviderContainer)> _pump(
  WidgetTester tester,
  SessionState session, {
  int cart = 0,
}) async {
  final container = ProviderContainer(overrides: [
    sessionProvider.overrideWith(() => _FakeSession(session)),
    cartItemCountProvider.overrideWith((ref) => cart),
    cartProvider.overrideWith(_EmptyCart.new),
    analyticsRepositoryProvider.overrideWithValue(_EmptyAnalytics()),
  ]);
  addTearDown(container.dispose);
  final router = container.read(routerProvider);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: container,
    child: MaterialApp.router(theme: buildAppTheme(), routerConfig: router),
  ));
  if (session is SessionSignedOut) {
    // Signed-out launches open the welcome page; continue to the shop tabs.
    await tester.pumpAndSettle();
    router.go('/');
  }
  return (router, container);
}

void main() {
  testWidgets('splash shows a loading indicator while checking',
      (tester) async {
    final (router, _) = await _pump(tester, const SessionChecking());
    await tester.pump();
    expect(router.state.uri.path, '/splash');
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
    expect(find.byType(NavigationBar), findsNothing);
  });

  testWidgets('unreachable server lands on login with the error message',
      (tester) async {
    final (router, _) = await _pump(tester,
        const SessionServerUnreachable('The server could not be reached'));
    await tester.pumpAndSettle();
    expect(router.state.uri.path, '/login');
    expect(find.text('The server could not be reached'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('cart badge is hidden at 0 and shows the count', (tester) async {
    await _pump(tester, const SessionSignedOut(), cart: 0);
    await tester.pumpAndSettle();
    expect(find.byType(Badge), findsNothing);
  });

  testWidgets('cart badge shows 5', (tester) async {
    await _pump(tester, const SessionSignedOut(), cart: 5);
    await tester.pumpAndSettle();
    expect(find.text('5'), findsOneWidget);
  });

  testWidgets('customer tabs switch branches', (tester) async {
    final (router, _) = await _pump(tester, const SessionSignedOut());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cart').last);
    await tester.pumpAndSettle();
    expect(router.state.uri.path, '/cart');
    await tester.tap(find.text('Home').last);
    await tester.pumpAndSettle();
    expect(router.state.uri.path, '/');
  });

  testWidgets('seller gets the same five staff tabs as admin', (tester) async {
    final (router, _) = await _pump(tester, const SessionSignedIn(_seller));
    await tester.pumpAndSettle();
    expect(router.state.uri.path, '/staff/dashboard');
    final bar = tester.widget<NavigationBar>(find.byType(NavigationBar));
    expect(bar.destinations.map((d) => (d as NavigationDestination).label),
        ['Dashboard', 'Orders', 'Products', 'Production', 'More']);
  });

  testWidgets('theme gives filled buttons an accessible tap target',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildAppTheme(),
      home: Scaffold(
        body: Center(
            child: FilledButton(onPressed: () {}, child: const Text('Go'))),
      ),
    ));
    final size = tester.getSize(find.byType(FilledButton));
    expect(size.height, greaterThanOrEqualTo(44));
  });
}
