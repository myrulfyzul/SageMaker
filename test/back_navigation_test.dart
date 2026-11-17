import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:sagemaker_flutter/core/widgets/back_fallback.dart';

/// A screen like Order tracking after a payment: opened with `go`, so nothing
/// is underneath it.
GoRouter _router() => GoRouter(initialLocation: '/', routes: [
      GoRoute(path: '/', builder: (_, __) => const Scaffold(body: Text('home'))),
      GoRoute(path: '/orders', builder: (_, __) => const Scaffold(body: Text('my orders'))),
      GoRoute(
        path: '/orders/:id',
        builder: (_, s) => BackFallback(
          fallback: '/orders',
          child: Scaffold(
            appBar: AppBar(
              leading: const FallbackBackButton(fallback: '/orders'),
              title: Text('tracking ${s.pathParameters['id']}'),
            ),
          ),
        ),
      ),
    ]);

Future<GoRouter> _pump(WidgetTester tester) async {
  final router = _router();
  addTearDown(router.dispose);
  await tester.pumpWidget(MaterialApp.router(routerConfig: router));
  return router;
}

void main() {
  testWidgets('back arrow opens the fallback when nothing is underneath',
      (tester) async {
    final router = await _pump(tester);
    router.go('/orders/SM-1');
    await tester.pumpAndSettle();
    expect(find.text('tracking SM-1'), findsOneWidget);
    await tester.tap(find.byKey(const Key('fallback-back')));
    await tester.pumpAndSettle();
    expect(find.text('my orders'), findsOneWidget);
  });

  testWidgets('back arrow simply goes back when the screen was pushed',
      (tester) async {
    final router = await _pump(tester);
    router.push('/orders/SM-2');
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('fallback-back')));
    await tester.pumpAndSettle();
    expect(find.text('home'), findsOneWidget);
  });

  testWidgets('the Android back button does not close the app', (tester) async {
    final router = await _pump(tester);
    router.go('/orders/SM-3');
    await tester.pumpAndSettle();
    // Same path as the system back button / back gesture.
    final handled = await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(handled, isTrue, reason: 'the app handled back instead of exiting');
    expect(find.text('my orders'), findsOneWidget);
  });
}
