// Task 17.10: customer widget tests that fill gaps left by the per-feature
// test files (login validation, cart error/retry/banners, favourites, shop
// and notifications states).
// Validates: Requirements 8.7, 11.8, 18.1, 31.2
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/legacy_local_store.dart';
import 'package:sagemaker_flutter/core/storage/token_store.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/auth/ui/login_screen.dart';
import 'package:sagemaker_flutter/features/cart/ui/cart_screen.dart';
import 'package:sagemaker_flutter/features/catalogue/ui/shop_screen.dart';
import 'package:sagemaker_flutter/features/favourites/ui/favourites_screen.dart';
import 'package:sagemaker_flutter/features/notifications/ui/notifications_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

class _FakeSession extends SessionNotifier {
  _FakeSession(this.initial);
  final SessionState initial;
  @override
  SessionState build() => initial;
}

const _customer = SessionSignedIn(
    AuthUser(id: 1, name: 'C', email: 'c@x.my', role: AppRole.customer));

Map<String, Object?> _product(String id, {int stock = 5}) => {
      'id': id,
      'name': 'Product $id',
      'category': {'id': 1, 'slug': 'cat', 'name': 'Cat'},
      'priceSen': 1000,
      'stock': {'status': 'in_stock', 'quantity': stock},
    };

Future<void> _pump(
  WidgetTester tester,
  Widget screen,
  Future<http.Response> Function(http.Request r) handler, {
  SessionState session = const SessionSignedOut(),
  Map<String, int> localCart = const {},
}) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues(
      {if (localCart.isNotEmpty) legacyCartKey: jsonEncode(localCart)});
  final prefs = await SharedPreferences.getInstance();
  await tester.pumpWidget(ProviderScope(
    overrides: [
      sessionProvider.overrideWith(() => _FakeSession(session)),
      tokenStoreProvider.overrideWithValue(MemoryTokenStore()),
      legacyLocalStoreProvider
          .overrideWith((ref) async => LegacyLocalStore(prefs)),
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 'tok')),
    ],
    child: MaterialApp(theme: buildAppTheme(), home: screen),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('Login form', () {
    testWidgets('empty submit shows field errors and sends no request',
        (tester) async {
      var calls = 0;
      await _pump(tester, const LoginScreen(), (_) async {
        calls++;
        return _json(401, {});
      });
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pump();
      expect(find.text('Enter your email'), findsOneWidget);
      expect(find.text('Enter your password'), findsOneWidget);
      expect(calls, 0);
    });

    testWidgets('password visibility can be toggled', (tester) async {
      await _pump(tester, const LoginScreen(), (_) async => _json(401, {}));
      bool obscured() => tester
          .widget<EditableText>(find.descendant(
              of: find.widgetWithText(TextFormField, 'Password'),
              matching: find.byType(EditableText)))
          .obscureText;
      expect(obscured(), isTrue);
      await tester.tap(find.byTooltip('Show password'));
      await tester.pump();
      expect(obscured(), isFalse);
    });
  });

  group('Cart screen', () {
    testWidgets('load failure shows error with retry, then recovers',
        (tester) async {
      var fail = true;
      await _pump(tester, const CartScreen(), (r) async {
        if (fail) return _json(500, {});
        return _json(200, _product('a'));
      }, localCart: {'a': 1});
      expect(find.text('Retry'), findsOneWidget);
      expect(find.text('Server error'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Product a'), findsOneWidget);
      expect(find.text('Retry'), findsNothing);
    });

    testWidgets('empty cart offers a single Explore products action',
        (tester) async {
      await _pump(tester, const CartScreen(), (_) async => _json(404, {}));
      expect(find.text('Your cart is empty.'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Explore products'),
          findsOneWidget);
      expect(find.byKey(const Key('checkout')), findsNothing);
    });

    testWidgets('increase beyond stock shows a message and keeps quantity',
        (tester) async {
      await _pump(tester, const CartScreen(),
          (r) async => _json(200, _product('a', stock: 2)),
          localCart: {'a': 2});
      expect(find.text('2'), findsOneWidget);
      await tester.tap(find.byTooltip('Increase quantity'));
      await tester.pumpAndSettle();
      expect(find.text('Only 2 available'), findsOneWidget);
      expect(find.text('2'), findsOneWidget);
    });

    testWidgets('decrease to zero removes the line (Req 11.8)',
        (tester) async {
      await _pump(tester, const CartScreen(),
          (r) async => _json(200, _product('a')),
          localCart: {'a': 1});
      expect(find.text('Product a'), findsOneWidget);
      await tester.tap(find.byTooltip('Decrease quantity'));
      await tester.pumpAndSettle();
      expect(find.text('Your cart is empty.'), findsOneWidget);
    });

    testWidgets('checkout is disabled when every line is unavailable',
        (tester) async {
      await _pump(tester, const CartScreen(), (_) async => _json(404, {}),
          localCart: {'gone': 1});
      expect(find.textContaining('Unavailable'), findsOneWidget);
      final btn = tester.widget<FilledButton>(find.byKey(const Key('checkout')));
      expect(btn.onPressed, isNull);
    });

    testWidgets('checkout is enabled with an available line', (tester) async {
      await _pump(tester, const CartScreen(),
          (r) async => _json(200, _product('a')),
          localCart: {'a': 1});
      final btn = tester.widget<FilledButton>(find.byKey(const Key('checkout')));
      expect(btn.onPressed, isNotNull);
    });

    testWidgets('not-merged notice is shown and can be dismissed',
        (tester) async {
      await _pump(tester, const CartScreen(), (r) async {
        if (r.url.path == '/api/cart/merge') {
          return _json(200, {
            'cart': {
              'lines': [
                {
                  'id': 1,
                  'productId': 'a',
                  'variationId': null,
                  'name': 'Product a',
                  'quantity': 20,
                  'unitPriceSen': 1000,
                  'lineTotalSen': 20000,
                  'available': true,
                  'availableQuantity': 50,
                }
              ],
              'subtotalSen': 20000,
              'deliveryFeeSen': 800,
              'grandTotalSen': 20800,
            },
            'notMerged': [
              {
                'productId': 'a',
                'variationId': null,
                'quantity': 3,
                'reason': 'line_limit'
              }
            ],
          });
        }
        return _json(500, {});
      }, session: _customer, localCart: {'a': 20});
      expect(find.byKey(const Key('not-merged')), findsOneWidget);
      await tester.tap(find.text('Dismiss'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('not-merged')), findsNothing);
    });

    testWidgets('failed merge shows a pending banner with retry',
        (tester) async {
      await _pump(tester, const CartScreen(), (r) async {
        if (r.method == 'GET') {
          return _json(200, {
            'lines': [],
            'subtotalSen': 0,
            'deliveryFeeSen': 0,
            'grandTotalSen': 0,
          });
        }
        return _json(500, {});
      }, session: _customer, localCart: {'a': 2});
      expect(find.byKey(const Key('merge-pending')), findsOneWidget);
      expect(find.text('Retry'), findsOneWidget);
    });
  });

  group('Favourites screen', () {
    testWidgets('empty state offers Explore products', (tester) async {
      await _pump(tester, const FavouritesScreen(),
          (_) async => _json(200, {'items': [], 'total': 0}),
          session: _customer);
      expect(find.textContaining('No favourites yet'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Explore products'),
          findsOneWidget);
    });

    testWidgets('load failure shows retry and recovers', (tester) async {
      var fail = true;
      await _pump(tester, const FavouritesScreen(), (_) async {
        return fail
            ? _json(500, {})
            : _json(200, {
                'items': [_product('a')],
                'total': 1
              });
      }, session: _customer);
      expect(find.text('Retry'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Product a'), findsOneWidget);
    });
  });

  group('Shop screen', () {
    testWidgets('lists products returned by the server', (tester) async {
      await _pump(tester, const ShopScreen(), (r) async {
        if (r.url.path == '/api/categories') return _json(200, []);
        return _json(200, {
          'items': [_product('a'), _product('b')],
          'total': 2
        });
      });
      expect(find.text('Product a'), findsOneWidget);
      expect(find.text('Product b'), findsOneWidget);
    });

    testWidgets('empty result offers Clear filters', (tester) async {
      await _pump(tester, const ShopScreen(), (r) async {
        if (r.url.path == '/api/categories') return _json(200, []);
        return _json(200, {'items': [], 'total': 0});
      });
      expect(find.text('No matching products.'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Clear filters'),
          findsOneWidget);
    });

    testWidgets('load failure shows retry and recovers', (tester) async {
      var fail = true;
      await _pump(tester, const ShopScreen(), (r) async {
        if (r.url.path == '/api/categories') return _json(200, []);
        return fail
            ? _json(500, {})
            : _json(200, {
                'items': [_product('a')],
                'total': 1
              });
      });
      expect(find.text('Retry'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Product a'), findsOneWidget);
    });
  });

  group('Notifications screen', () {
    testWidgets('empty state offers Explore products and disables mark all',
        (tester) async {
      await _pump(tester, const NotificationsScreen(),
          (_) async => _json(200, {'items': [], 'total': 0, 'unreadCount': 0}),
          session: _customer);
      expect(find.text('You have no notifications.'), findsOneWidget);
      expect(find.widgetWithText(FilledButton, 'Explore products'),
          findsOneWidget);
      final markAll = tester
          .widget<TextButton>(find.widgetWithText(TextButton, 'Mark all read'));
      expect(markAll.onPressed, isNull);
    });
  });
}
