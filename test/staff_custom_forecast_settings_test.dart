import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/admin/custom_orders/data/staff_custom_orders.dart';
import 'package:sagemaker_flutter/features/admin/custom_orders/ui/staff_custom_orders_screen.dart';
import 'package:sagemaker_flutter/features/admin/forecasting/data/forecast_models.dart';
import 'package:sagemaker_flutter/features/admin/forecasting/ui/forecasting_screen.dart';
import 'package:sagemaker_flutter/features/admin/notifications/ui/staff_notifications_screen.dart';
import 'package:sagemaker_flutter/features/admin/settings/state/staff_settings_provider.dart';
import 'package:sagemaker_flutter/features/admin/settings/ui/staff_settings_screen.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

Future<void> _pump(WidgetTester tester, Widget screen,
    Future<http.Response> Function(http.Request r) handler) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ProviderScope(
    key: UniqueKey(),
    overrides: [
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 't')),
    ],
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

Map<String, Object?> _co(int id, String status, {int? artisan}) => {
      'id': id,
      'productType': 'Tote',
      'description': 'A custom tote bag',
      'quantity': 2,
      'preferredDate': '2030-01-01',
      'status': status,
      'artisanId': artisan,
    };

Map<String, Object?> _forecast(
        {bool evaluated = true, bool synthetic = true}) =>
    {
      'productId': 'p1',
      'synthetic': synthetic,
      'history': [
        for (var i = 1; i <= 6; i++) {'month': '2025-0$i', 'units': i}
      ],
      'baseline': {
        'forecast': [
          for (var i = 7; i <= 9; i++) {'month': '2025-0$i', 'units': 5}
        ]
      },
      'candidate': evaluated
          ? {
              'forecast': [
                for (var i = 7; i <= 9; i++) {'month': '2025-0$i', 'units': 7}
              ]
            }
          : null,
      'evaluation': evaluated
          ? {
              'available': true,
              'baseline': {'mae': 1.5, 'rmse': 2.25},
              'candidate': {'mae': 0.5, 'rmse': 0.75},
            }
          : {'available': false, 'reason': 'insufficient_history'},
      'selectedModel': evaluated ? 'candidate' : 'baseline',
      'replenish': true,
      'methodology': {
        'data': 'Monthly units.',
        'models': 'Baseline and candidate.',
        'evaluation': 'Hold out two months.',
        'limitations': 'Rough.',
      },
    };

void main() {
  test('validators', () {
    expect(validateRejectReason('    abcd   '), isNotNull);
    expect(validateRejectReason('abcde'), isNull);
    expect(validateRejectReason('a' * 501), isNotNull);
    expect(validateDefaultThreshold('-1'), isNotNull);
    expect(validateDefaultThreshold('0'), isNull);
    expect(validateDefaultThreshold('1000000000'), isNotNull);
  });

  test('state machine actions', () {
    StaffCustomOrder o(String s, {int? a}) =>
        StaffCustomOrder.fromJson(_co(1, s, artisan: a));
    expect(o('submitted').canAccept, isTrue);
    expect(o('accepted').canAssign, isTrue);
    expect(o('accepted', a: 3).canAssign, isFalse);
    expect(o('accepted').nextStatus, 'in_progress');
    expect(o('rejected').nextStatus, isNull);
  });

  test('forecast parsing handles insufficient history', () {
    final f = Forecast.fromJson(_forecast(evaluated: false));
    expect(f.candidate, isNull);
    expect(f.evaluationAvailable, isFalse);
    expect(f.baselineMetrics, isNull);
    expect(forecastSummary(f), contains('Baseline forecast'));
  });

  testWidgets('custom orders list, reject validation and accept call',
      (tester) async {
    final calls = <String>[];
    await _pump(tester, const StaffCustomOrdersScreen(), (r) async {
      if (r.method == 'POST') {
        calls.add('${r.url.path} ${r.body}');
        return _json(200, _co(1, 'accepted'));
      }
      return _json(200, {
        'items': [_co(1, 'submitted'), _co(2, 'accepted')],
        'total': 2,
      });
    });
    expect(find.byKey(const ValueKey('accept-1')), findsOneWidget);
    expect(find.byKey(const ValueKey('assign-2')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('reject-1')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'no');
    await tester.tap(find.descendant(
        of: find.byType(AlertDialog),
        matching: find.widgetWithText(FilledButton, 'Reject')));
    await tester.pumpAndSettle();
    expect(find.text('Reason must be 5 to 500 characters'), findsOneWidget);
    expect(calls, isEmpty);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('accept-1')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '12.50');
    await tester.tap(find.descendant(
        of: find.byType(AlertDialog),
        matching: find.widgetWithText(FilledButton, 'Accept')));
    await tester.pumpAndSettle();
    expect(calls.single, contains('/api/staff/custom-orders/1/accept'));
    expect(calls.single, contains('1250'));
  });

  testWidgets('forecast shows metrics, flag, notices and methodology',
      (tester) async {
    await _pump(tester, const ForecastingScreen(initialProductId: 'p1'),
        (r) async {
      if (r.url.path == '/api/staff/forecast/p1') {
        return _json(200, _forecast());
      }
      return _json(200, {
        'items': [
          {
            'productId': 'p1',
            'name': 'Tote',
            'quantity': 1,
            'lowStockThreshold': 2
          }
        ],
        'total': 1,
      });
    });
    expect(find.byKey(const ValueKey('synthetic-notice')), findsOneWidget);
    expect(find.byKey(const ValueKey('replenish-flag')), findsOneWidget);
    expect(find.textContaining('MAE 0.5'), findsOneWidget);
    expect(find.textContaining('Hold out two months.'), findsOneWidget);
    expect(find.textContaining('estimates from your sales history'), findsOneWidget);
  });

  testWidgets('forecast shows insufficient history and error hides chart',
      (tester) async {
    await _pump(tester, const ForecastingScreen(initialProductId: 'p1'),
        (r) async {
      if (r.url.path == '/api/staff/forecast/p1') {
        return _json(200, _forecast(evaluated: false, synthetic: false));
      }
      return _json(200, {
        'items': [
          {
            'productId': 'p1',
            'name': 'Tote',
            'quantity': 1,
            'lowStockThreshold': 2
          }
        ],
        'total': 1,
      });
    });
    expect(find.byKey(const ValueKey('insufficient')), findsOneWidget);
    expect(find.byKey(const ValueKey('synthetic-notice')), findsNothing);

    await _pump(tester, const ForecastingScreen(initialProductId: 'p1'),
        (r) async {
      if (r.url.path == '/api/staff/forecast/p1') {
        return _json(500, {'code': 'forecast_failed', 'message': 'x'});
      }
      return _json(200, {
        'items': [
          {
            'productId': 'p1',
            'name': 'Tote',
            'quantity': 1,
            'lowStockThreshold': 2
          }
        ],
        'total': 1,
      });
    });
    expect(find.text('Retry'), findsOneWidget);
    expect(find.textContaining('MAE'), findsNothing);
  });

  testWidgets('settings saves the default threshold', (tester) async {
    String? sent;
    await _pump(tester, const StaffSettingsScreen(), (r) async {
      if (r.method == 'PUT') {
        sent = r.body;
        return _json(200, {'defaultLowStockThreshold': 9});
      }
      return _json(200, {'defaultLowStockThreshold': 5});
    });
    expect(find.text('5'), findsOneWidget);
    await tester.enterText(
        find.byKey(const ValueKey('default-threshold')), 'x');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(sent, isNull);
    await tester.enterText(
        find.byKey(const ValueKey('default-threshold')), '9');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(jsonDecode(sent!), {'defaultLowStockThreshold': 9});
    expect(find.text('Settings saved.'), findsOneWidget);
  });

  testWidgets('staff notifications list and empty state', (tester) async {
    await _pump(tester, const StaffNotificationsScreen(), (r) async {
      return _json(200, {
        'items': [
          {
            'id': 1,
            'type': 't',
            'title': 'New order',
            'body': 'b',
            'isRead': false
          }
        ],
        'unreadCount': 1,
        'total': 1,
      });
    });
    expect(find.text('New order'), findsOneWidget);

    await _pump(tester, const StaffNotificationsScreen(), (r) async {
      return _json(200, {'items': [], 'unreadCount': 0, 'total': 0});
    });
    expect(find.text('You have no notifications.'), findsOneWidget);
  });
}
