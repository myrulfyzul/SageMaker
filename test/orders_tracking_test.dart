import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/legacy_local_store.dart';
import 'package:sagemaker_flutter/features/orders/data/order_models.dart';
import 'package:sagemaker_flutter/features/orders/ui/my_orders_screen.dart';
import 'package:sagemaker_flutter/features/orders/ui/order_tracking_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

Map<String, Object?> _summary(String id, {String status = 'placed'}) => {
      'id': id,
      'status': status,
      'paymentStatus': 'paid',
      'paymentMethod': 'card',
      'totalSen': 7800,
      'itemCount': 2,
      'createdAt': '2025-06-01T03:04:05Z',
    };

Map<String, Object?> _detail({
  String status = 'placed',
  List<Map<String, Object?>>? history,
  String? production,
  String? shipping,
}) =>
    {
      'id': 'SM-1',
      'status': status,
      'paymentStatus': 'paid',
      'paymentMethod': 'card',
      'lines': [
        {
          'name': 'Busy Book',
          'quantity': 2,
          'unitPriceSen': 3500,
          'lineTotalSen': 7000
        }
      ],
      'subtotalSen': 7000,
      'shippingFeeSen': 800,
      'totalSen': 7800,
      'delivery': {
        'name': 'Aina',
        'phone': '0123456789',
        'email': 'a@x.my',
        'address': '1 Jalan Satu',
        'postcode': '50000',
        'state': 'Kuala Lumpur',
        'notes': null
      },
      'shippingReference': shipping,
      'productionLabel': production,
      'history': history ??
          [
            {'status': 'placed', 'at': '2025-06-01T03:04:05Z'}
          ],
      'isDemo': true,
    };

Future<void> _pump(
  WidgetTester tester,
  Widget screen,
  Future<http.Response> Function(http.Request r) handler, {
  Map<String, Object> prefs = const {},
}) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues(prefs);
  final sp = await SharedPreferences.getInstance();
  await tester.pumpWidget(ProviderScope(
    overrides: [
      legacyLocalStoreProvider
          .overrideWith((ref) async => LegacyLocalStore(sp)),
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 't')),
    ],
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('buildTimeline', () {
    test('marks steps with history as reached and the rest as not yet reached',
        () {
      final t = buildTimeline('confirmed', [
        OrderHistoryEntry(status: 'placed', at: DateTime(2025, 6, 1, 10)),
        OrderHistoryEntry(status: 'confirmed', at: DateTime(2025, 6, 2, 11)),
      ]);
      expect(t.map((s) => s.status), timelineStatuses);
      expect(t.map((s) => s.reached), [true, true, false, false, false]);
      expect(t[1].at, DateTime(2025, 6, 2, 11));
      expect(t[2].at, isNull);
    });

    test('cancelled keeps reached steps and replaces unreached ones', () {
      final t = buildTimeline('cancelled', [
        OrderHistoryEntry(status: 'placed', at: DateTime(2025, 6, 1)),
        OrderHistoryEntry(status: 'cancelled', at: DateTime(2025, 6, 3)),
      ]);
      expect(t.map((s) => s.status), ['placed', 'cancelled']);
      expect(t.last.terminal, isTrue);
      expect(t.last.at, DateTime(2025, 6, 3));
    });

    test('payment_failed terminal state and legacy packing alias', () {
      final f = buildTimeline('payment_failed', [
        OrderHistoryEntry(status: 'placed', at: DateTime(2025, 6, 1)),
        OrderHistoryEntry(
            status: 'payment_failed', at: DateTime(2025, 6, 1, 1)),
      ]);
      expect(f.last.label, 'Payment failed');
      final p = buildTimeline('packing', [
        OrderHistoryEntry.fromJson({'status': 'packing', 'at': null})
      ]);
      expect(p.firstWhere((s) => s.status == 'preparing').reached, isTrue);
    });
  });

  group('My Orders', () {
    testWidgets('shows server orders, pages with Load more', (tester) async {
      final offsets = <String?>[];
      await _pump(tester, const MyOrdersScreen(), (r) async {
        offsets.add(r.url.queryParameters['offset']);
        final first = r.url.queryParameters['offset'] == '0';
        return _json(200, {
          'items': [_summary(first ? 'SM-A' : 'SM-B')],
          'hasMore': first,
        });
      });
      expect(find.text('SM-A'), findsOneWidget);
      await tester.tap(find.text('Load more'));
      await tester.pumpAndSettle();
      expect(find.text('SM-A'), findsOneWidget);
      expect(find.text('SM-B'), findsOneWidget);
      expect(find.text('Load more'), findsNothing);
      expect(offsets, ['0', '1']);
    });

    testWidgets('empty state when there are no orders', (tester) async {
      await _pump(tester, const MyOrdersScreen(),
          (_) async => _json(200, {'items': [], 'hasMore': false}));
      expect(find.text('You have no orders yet.'), findsOneWidget);
      expect(find.text('Explore products'), findsOneWidget);
    });

    testWidgets('failed refresh keeps the last data and offers retry',
        (tester) async {
      var fail = false;
      await _pump(
          tester,
          const MyOrdersScreen(),
          (_) async => fail
              ? _json(500, {
                  'error': {'code': 'x', 'message': 'boom'}
                })
              : _json(200, {
                  'items': [_summary('SM-A')],
                  'hasMore': false
                }));
      fail = true;
      await tester.tap(find.byTooltip('Refresh'));
      await tester.pumpAndSettle();
      expect(find.text('SM-A'), findsOneWidget);
      expect(find.textContaining('Refresh failed'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Refresh failed'), findsNothing);
      expect(find.text('SM-A'), findsOneWidget);
    });

    testWidgets('lists legacy guest orders in their own section',
        (tester) async {
      await _pump(
        tester,
        const MyOrdersScreen(),
        (_) async => _json(200, {'items': [], 'hasMore': false}),
        prefs: {
          legacyOrdersKey: jsonEncode([
            {'id': 'DEMO-1234567890', 'token': 'tok'}
          ])
        },
      );
      expect(find.text('Legacy guest orders'), findsOneWidget);
      expect(find.text('DEMO-1234567890'), findsOneWidget);
    });

    testWidgets('first load error shows retry', (tester) async {
      await _pump(
          tester,
          const MyOrdersScreen(),
          (_) async => _json(500, {
                'error': {'code': 'x', 'message': 'boom'}
              }));
      expect(find.text('Server error'), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
    });
  });

  group('Order tracking', () {
    testWidgets(
        'renders timeline, shipping reference and separate production label',
        (tester) async {
      await _pump(
        tester,
        const OrderTrackingScreen(orderId: 'SM-1'),
        (_) async => _json(
            200,
            _detail(
                status: 'shipped',
                shipping: 'REF123',
                production: 'In production',
                history: [
                  {'status': 'placed', 'at': '2025-06-01T03:04:05Z'},
                  {'status': 'confirmed', 'at': '2025-06-02T03:04:05Z'},
                  {'status': 'preparing', 'at': '2025-06-03T03:04:05Z'},
                  {'status': 'shipped', 'at': '2025-06-04T03:04:05Z'},
                ])),
      );
      expect(find.text('Status: Shipped'), findsOneWidget);
      expect(find.text('Not yet reached'), findsOneWidget); // Delivered only
      expect(find.text('REF123'), findsOneWidget);
      expect(find.byKey(const ValueKey('production-label')), findsOneWidget);
      expect(find.text('In production'), findsOneWidget);
      expect(find.text('Busy Book'), findsOneWidget);
      expect(find.text('RM 78.00'), findsOneWidget);
    });

    testWidgets('no production label and empty shipping placeholder',
        (tester) async {
      await _pump(tester, const OrderTrackingScreen(orderId: 'SM-1'),
          (_) async => _json(200, _detail()));
      expect(find.byKey(const ValueKey('production-label')), findsNothing);
      expect(find.text('Not available yet'), findsOneWidget);
    });

    testWidgets('cancelled order shows the terminal state', (tester) async {
      await _pump(
        tester,
        const OrderTrackingScreen(orderId: 'SM-1'),
        (_) async => _json(
            200,
            _detail(status: 'cancelled', history: [
              {'status': 'placed', 'at': '2025-06-01T03:04:05Z'},
              {'status': 'cancelled', 'at': '2025-06-02T03:04:05Z'},
            ])),
      );
      expect(find.byKey(const ValueKey('step-cancelled')), findsOneWidget);
      expect(find.byKey(const ValueKey('step-delivered')), findsNothing);
    });

    testWidgets('failed reload keeps data; not found shows message',
        (tester) async {
      var fail = false;
      await _pump(
          tester,
          const OrderTrackingScreen(orderId: 'SM-1'),
          (_) async => fail
              ? _json(500, {
                  'error': {'message': 'x'}
                })
              : _json(200, _detail()));
      fail = true;
      await tester.tap(find.byTooltip('Refresh'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Refresh failed'), findsOneWidget);
      expect(find.text('Status: Placed'), findsOneWidget);
    });

    testWidgets('unknown order shows not found', (tester) async {
      await _pump(
          tester,
          const OrderTrackingScreen(orderId: 'SM-9'),
          (_) async => _json(404, {
                'error': {'code': 'not_found', 'message': 'Not found'}
              }));
      expect(find.text('Order not found.'), findsOneWidget);
    });
  });
}
