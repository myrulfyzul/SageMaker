import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/core/widgets/async_value_view.dart';
import 'package:sagemaker_flutter/core/widgets/badge_count.dart';

Widget host(Widget child) =>
    MaterialApp(theme: buildAppTheme(), home: Scaffold(body: child));

void main() {
  test('theme uses brand colours, radius and contrast', () {
    final t = buildAppTheme();
    expect(t.useMaterial3, isTrue);
    expect(t.colorScheme.primary, kPrimary);
    expect(t.scaffoldBackgroundColor, kBackground);
    expect(t.cardTheme.color, kCard);
    final r = (t.cardTheme.shape! as RoundedRectangleBorder).borderRadius
        as BorderRadius;
    expect(r.topLeft.x, inInclusiveRange(12, 16));
    expect(contrastRatio(kText, kBackground), greaterThanOrEqualTo(4.5));
    expect(contrastRatio(Colors.white, kPrimary), greaterThanOrEqualTo(4.5));
    expect(contrastRatio(kText, kAccent), greaterThanOrEqualTo(4.5));
  });

  testWidgets('loading shows indicator', (tester) async {
    await tester.pumpWidget(host(AsyncValueView<int>(
      value: const AsyncLoading(),
      data: (_) => const Text('data'),
      onRetry: () {},
      onEmptyAction: () {},
    )));
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('data replaces loading indicator', (tester) async {
    await tester.pumpWidget(host(AsyncValueView<int>(
      value: const AsyncData(1),
      data: (_) => const Text('data'),
      onRetry: () {},
      onEmptyAction: () {},
    )));
    expect(find.byType(CircularProgressIndicator), findsNothing);
    expect(find.text('data'), findsOneWidget);
  });

  testWidgets('error shows reason and retry', (tester) async {
    var retried = 0;
    await tester.pumpWidget(host(AsyncValueView<int>(
      value: AsyncError(Exception('x'), StackTrace.empty),
      data: (_) => const Text('data'),
      onRetry: () => retried++,
      onEmptyAction: () {},
      errorMessage: (_) => 'Network unavailable',
    )));
    expect(find.text('Network unavailable'), findsOneWidget);
    await tester.tap(find.text('Retry'));
    expect(retried, 1);
  });

  testWidgets('empty shows message and exactly one action', (tester) async {
    var taps = 0;
    await tester.pumpWidget(host(AsyncValueView<List<int>>(
      value: const AsyncData([]),
      data: (_) => const Text('data'),
      isEmpty: (d) => d.isEmpty,
      emptyMessage: 'No items',
      emptyActionLabel: 'Go shopping',
      onRetry: () {},
      onEmptyAction: () => taps++,
    )));
    expect(find.text('No items'), findsOneWidget);
    expect(find.byType(FilledButton), findsOneWidget);
    await tester.tap(find.text('Go shopping'));
    expect(taps, 1);
  });

  testWidgets('BadgeCount hides 0, shows 5 and 99+', (tester) async {
    Future<void> show(int n) => tester.pumpWidget(
        host(BadgeCount(count: n, child: const Icon(Icons.shopping_cart))));
    await show(0);
    expect(find.byType(Badge), findsNothing);
    await show(5);
    expect(find.text('5'), findsOneWidget);
    await show(150);
    expect(find.text('99+'), findsOneWidget);
  });


}
