// Task 19.6: gap-filling widget tests for staff features (loading, empty,
// error/retry, role restrictions, validation). Complements the per-feature
// staff test files.
//
// Validates: Requirements 19.9, 24.13, 31.2
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/app/role_permissions.dart';
import 'package:sagemaker_flutter/app/shells/staff_shell.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/admin/artisans/ui/artisans_screen.dart';
import 'package:sagemaker_flutter/features/admin/custom_orders/ui/staff_custom_orders_screen.dart';
import 'package:sagemaker_flutter/features/admin/inventory/ui/inventory_screen.dart';
import 'package:sagemaker_flutter/features/admin/notifications/ui/staff_notifications_screen.dart';
import 'package:sagemaker_flutter/features/admin/orders/ui/staff_orders_screen.dart';
import 'package:sagemaker_flutter/features/admin/production/state/production_provider.dart';
import 'package:sagemaker_flutter/features/admin/production/ui/production_screen.dart';
import 'package:sagemaker_flutter/features/admin/products/ui/admin_products_screen.dart';
import 'package:sagemaker_flutter/features/admin/settings/ui/staff_settings_screen.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

http.Response _fail() => _json(500, {
      'error': {'code': 'server_error', 'message': 'Server error'}
    });

Future<void> _pump(WidgetTester tester, Widget screen,
    Future<http.Response> Function(http.Request r) handler,
    {List<Override> extra = const []}) async {
  tester.view.physicalSize = const Size(900, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ProviderScope(
    key: UniqueKey(),
    overrides: [
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 't')),
      ...extra,
    ],
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

class _FakeSession extends SessionNotifier {
  _FakeSession(this.initial);
  final SessionState initial;
  @override
  SessionState build() => initial;
}

SessionState _signedIn(AppRole role) =>
    SessionSignedIn(AuthUser(id: 1, name: 'U', email: 'u@x.my', role: role));

/// Fails every request until [flip] is called (providers auto-retry, so a
/// single failure would be absorbed), then serves [ok]. Used with [_flip].
bool _failing = true;
void _flip() => _failing = false;

Future<http.Response> Function(http.Request) _failThen(Object ok) {
  _failing = true;
  return (r) async => _failing ? _fail() : _json(200, ok);
}

void main() {
  group('role restrictions', () {
    test('artisan can open Production only; seller and admin open all', () {
      expect(
          RolePermissions.canOpenStaffPath(
              AppRole.artisan, '/staff/production'),
          isTrue);
      for (final p in [
        '/staff/dashboard',
        '/staff/orders',
        '/staff/products',
        '/staff/more',
        '/staff/more/settings',
      ]) {
        expect(RolePermissions.canOpenStaffPath(AppRole.artisan, p), isFalse,
            reason: p);
        expect(RolePermissions.canOpenStaffPath(AppRole.seller, p), isTrue);
        expect(RolePermissions.canOpenStaffPath(AppRole.admin, p), isTrue);
      }
      expect(
          RolePermissions.canOpenStaffPath(AppRole.customer, '/staff/orders'),
          isFalse);
    });

    testWidgets('More lists the six entries in order for seller and admin',
        (tester) async {
      for (final role in [AppRole.seller, AppRole.admin]) {
        await tester.pumpWidget(ProviderScope(
          key: UniqueKey(),
          overrides: [
            sessionProvider.overrideWith(() => _FakeSession(_signedIn(role))),
          ],
          child: const MaterialApp(home: Scaffold(body: StaffMoreScreen())),
        ));
        await tester.pump();
        final titles = tester
            .widgetList<ListTile>(find.byType(ListTile))
            .map((t) => (t.title as Text).data)
            .toList();
        expect(titles, [
          'Inventory',
          'Artisans',
          'Analytics',
          'Forecasting',
          'Notifications',
          'Settings',
        ]);
      }
    });

    testWidgets('More is empty for the artisan role', (tester) async {
      await tester.pumpWidget(ProviderScope(
        overrides: [
          sessionProvider
              .overrideWith(() => _FakeSession(_signedIn(AppRole.artisan))),
        ],
        child: const MaterialApp(home: Scaffold(body: StaffMoreScreen())),
      ));
      await tester.pump();
      expect(find.byType(ListTile), findsNothing);
    });
  });

  group('staff orders', () {
    testWidgets('empty result shows the no-match message', (tester) async {
      await _pump(tester, const StaffOrdersScreen(),
          (r) async => _json(200, {'items': [], 'hasMore': false}));
      expect(find.text('No orders match.'), findsOneWidget);
    });

    testWidgets('load failure shows retry that recovers', (tester) async {
      await _pump(tester, const StaffOrdersScreen(),
          _failThen({'items': [], 'hasMore': false}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Retry'), findsNothing);
      expect(find.text('No orders match.'), findsOneWidget);
    });
  });

  group('production', () {
    testWidgets('empty state for staff offers refresh', (tester) async {
      var calls = 0;
      await _pump(tester, const ProductionScreen(), (r) async {
        calls++;
        return _json(200, {'items': [], 'total': 0});
      });
      expect(find.text('No production jobs yet.'), findsOneWidget);
      final before = calls;
      await tester.tap(find.widgetWithText(FilledButton, 'Refresh'));
      await tester.pumpAndSettle();
      expect(calls, greaterThan(before));
    });

    testWidgets(
        'empty state for artisan has its own message and no artisan filter',
        (tester) async {
      await _pump(tester, const ProductionScreen(),
          (r) async => _json(200, {'items': [], 'total': 0}),
          extra: [productionRoleProvider.overrideWithValue(AppRole.artisan)]);
      expect(find.text('No jobs are assigned to you yet.'), findsOneWidget);
      expect(find.byKey(const ValueKey('filter-artisan-all')), findsNothing);
    });

    testWidgets('load failure shows retry that recovers', (tester) async {
      await _pump(tester, const ProductionScreen(),
          _failThen({'items': [], 'total': 0}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('No production jobs yet.'), findsOneWidget);
    });
  });

  group('products and inventory', () {
    testWidgets('products empty state offers New product', (tester) async {
      await _pump(tester, const Scaffold(body: AdminProductsScreen()),
          (r) async => _json(200, {'items': [], 'total': 0}));
      expect(find.text('No products yet.'), findsOneWidget);
      expect(find.text('New product'), findsWidgets);
    });

    testWidgets('products failure shows retry that recovers', (tester) async {
      await _pump(tester, const Scaffold(body: AdminProductsScreen()),
          _failThen({'items': [], 'total': 0}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('No products yet.'), findsOneWidget);
    });

    testWidgets('inventory empty state and failure with retry', (tester) async {
      await _pump(tester, const InventoryScreen(),
          (r) async => _json(200, {'items': [], 'total': 0}));
      expect(find.text('No stock records yet.'), findsOneWidget);

      await _pump(tester, const InventoryScreen(),
          _failThen({'items': [], 'total': 0}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('No stock records yet.'), findsOneWidget);
    });
  });

  group('artisans', () {
    testWidgets('empty state and failure with retry', (tester) async {
      await _pump(tester, const ArtisansScreen(),
          (r) async => _json(200, {'items': [], 'total': 0}));
      expect(find.text('No artisans yet.'), findsOneWidget);

      await _pump(
          tester, const ArtisansScreen(), _failThen({'items': [], 'total': 0}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('No artisans yet.'), findsOneWidget);
    });
  });

  group('custom orders', () {
    testWidgets('empty state, then failure with retry', (tester) async {
      await _pump(tester, const StaffCustomOrdersScreen(),
          (r) async => _json(200, {'items': [], 'total': 0}));
      expect(find.text('No custom orders yet. Total: 0'), findsOneWidget);

      await _pump(tester, const StaffCustomOrdersScreen(),
          _failThen({'items': [], 'total': 0}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('No custom orders yet. Total: 0'), findsOneWidget);
    });
  });

  group('settings', () {
    testWidgets('load failure shows retry that recovers', (tester) async {
      await _pump(tester, const StaffSettingsScreen(),
          _failThen({'defaultLowStockThreshold': 4}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('default-threshold')), findsOneWidget);
      expect(find.text('4'), findsOneWidget);
    });

    testWidgets('negative threshold is rejected without a request',
        (tester) async {
      var puts = 0;
      await _pump(tester, const StaffSettingsScreen(), (r) async {
        if (r.method == 'PUT') puts++;
        return _json(200, {'defaultLowStockThreshold': 5});
      });
      await tester.enterText(
          find.byKey(const ValueKey('default-threshold')), '-1');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(puts, 0);
      expect(find.text('Settings saved.'), findsNothing);
    });
  });

  group('staff notifications', () {
    testWidgets('failure shows retry that recovers to the empty state',
        (tester) async {
      await _pump(tester, const StaffNotificationsScreen(),
          _failThen({'items': [], 'unreadCount': 0, 'total': 0}));
      expect(find.text('Retry'), findsOneWidget);
      _flip();
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('You have no notifications.'), findsOneWidget);
    });
  });
}
