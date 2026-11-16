import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/admin/orders/data/staff_orders_repository.dart';
import 'package:sagemaker_flutter/features/admin/orders/ui/staff_order_detail_screen.dart';
import 'package:sagemaker_flutter/features/admin/orders/ui/staff_orders_screen.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

Map<String, Object?> _row(String id, String status, String name) => {
      'id': id,
      'status': status,
      'customerName': name,
      'paymentStatus': 'paid',
      'paymentMethod': 'card',
      'totalSen': 7800,
      'itemCount': 2,
      'createdAt': '2025-06-01T03:04:05Z',
    };

Map<String, Object?> _detail(String status, {String? ref}) => {
      ..._row('SM-1', status, 'Aina'),
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
      'delivery': {
        'name': 'Aina',
        'phone': '0123456789',
        'email': 'a@x.my',
        'address': '1 Jalan Satu',
      },
      'shippingReference': ref,
      'history': [
        {'status': 'placed', 'at': '2025-06-01T03:04:05Z'}
      ],
    };

Future<void> _pump(WidgetTester tester, Widget screen,
    Future<http.Response> Function(http.Request r) handler) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 't')),
    ],
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('helpers', () {
    test('forward transitions and cancellation rules', () {
      expect(nextStaffStatus('placed'), 'confirmed');
      expect(nextStaffStatus('packing'), 'shipped');
      expect(nextStaffStatus('delivered'), isNull);
      expect(nextStaffStatus('cancelled'), isNull);
      expect(canCancelStaffOrder('preparing'), isTrue);
      expect(canCancelStaffOrder('packing'), isTrue);
      expect(canCancelStaffOrder('shipped'), isFalse);
    });

    test('length validators', () {
      expect(validateShippingReference('ab'), isNotNull);
      expect(validateShippingReference('abc'), isNull);
      expect(validateShippingReference('a' * 81), isNotNull);
      expect(validateCancelReason('  x '), isNotNull);
      expect(validateCancelReason('a' * 500), isNull);
      expect(validateCancelReason('a' * 501), isNotNull);
    });

    test('legacy packing summary reads as preparing', () {
      expect(
          StaffOrderSummary.fromJson(_row('SM-9', 'packing', 'Old')).status,
          'preparing');
    });
  });

  testWidgets('list sends status filter and search, shows legacy order',
      (tester) async {
    final requests = <Uri>[];
    await _pump(tester, const StaffOrdersScreen(), (r) async {
      requests.add(r.url);
      return _json(200, {
        'items': [
          _row('SM-1', 'placed', 'Aina'),
          _row('SM-0', 'packing', 'Legacy Guest'),
        ],
        'hasMore': false,
      });
    });
    expect(find.text('SM-0 · Legacy Guest'), findsOneWidget);
    expect(find.textContaining('Preparing'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('filter-Shipped')));
    await tester.pumpAndSettle();
    expect(requests.last.queryParameters['status'], 'shipped');

    await tester.enterText(
        find.byKey(const ValueKey('staff-orders-search')), 'aina');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(requests.last.queryParameters['q'], 'aina');
    expect(requests.last.queryParameters['status'], 'shipped');
  });

  testWidgets('shipping requires a reference then posts it', (tester) async {
    Map<String, dynamic>? posted;
    await _pump(tester, const StaffOrderDetailScreen(orderId: 'SM-1'),
        (r) async {
      if (r.method == 'POST') {
        posted = jsonDecode(r.body) as Map<String, dynamic>;
        return _json(200, _detail('shipped', ref: 'TRK123'));
      }
      return _json(200, _detail('preparing'));
    });
    await tester.tap(find.byKey(const ValueKey('advance-button')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('prompt-confirm')));
    await tester.pumpAndSettle();
    expect(find.text('Enter 3 to 80 characters'), findsOneWidget);
    expect(posted, isNull);

    await tester.enterText(
        find.byKey(const ValueKey('shipping-reference-field')), 'TRK123');
    await tester.tap(find.byKey(const ValueKey('prompt-confirm')));
    await tester.pumpAndSettle();
    expect(posted, {'status': 'shipped', 'shipping_reference': 'TRK123'});
    expect(find.text('Shipped'), findsWidgets);
  });

  testWidgets('cancel asks for a reason and 409 shows both statuses',
      (tester) async {
    Map<String, dynamic>? posted;
    await _pump(tester, const StaffOrderDetailScreen(orderId: 'SM-1'),
        (r) async {
      if (r.method == 'POST') {
        posted = jsonDecode(r.body) as Map<String, dynamic>;
        return _json(409, {
          'error': {
            'code': 'invalid_transition',
            'message': 'Cannot change order status from shipped to cancelled',
            'details': [
              {'current': 'shipped', 'requested': 'cancelled'}
            ],
          }
        });
      }
      return _json(200, _detail('placed'));
    });
    await tester.tap(find.byKey(const ValueKey('cancel-button')));
    await tester.pumpAndSettle();
    await tester.enterText(
        find.byKey(const ValueKey('cancel-reason-field')), 'Out of stock');
    await tester.tap(find.byKey(const ValueKey('prompt-confirm')));
    await tester.pumpAndSettle();
    expect(posted, {'status': 'cancelled', 'reason': 'Out of stock'});
    expect(find.byKey(const ValueKey('status-error')), findsOneWidget);
    expect(find.textContaining('from Shipped to Cancelled'), findsOneWidget);
    expect(find.text('Placed'), findsWidgets);
  });
}
