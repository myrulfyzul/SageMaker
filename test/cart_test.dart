import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/badge.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/legacy_local_store.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/cart/state/cart_provider.dart';
import 'package:sagemaker_flutter/features/cart/ui/cart_screen.dart';
import 'package:sagemaker_flutter/features/catalogue/data/catalogue_models.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeSession extends SessionNotifier {
  _FakeSession(this.initial);
  final SessionState initial;
  @override
  SessionState build() => initial;
}

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

const _customer = SessionSignedIn(
    AuthUser(id: 1, name: 'C', email: 'c@x.my', role: AppRole.customer));

Map<String, Object?> _line(String pid, int qty,
        {bool available = true, int id = 1}) =>
    {
      'id': id,
      'productId': pid,
      'variationId': null,
      'name': 'Product $pid',
      'quantity': qty,
      'unitPriceSen': 1000,
      'lineTotalSen': 1000 * qty,
      'available': available,
      'availableQuantity': 5,
    };

Map<String, Object?> _cart(List<Map<String, Object?>> lines) {
  final sub = lines
      .where((l) => l['available'] == true)
      .fold<int>(0, (s, l) => s + (l['lineTotalSen'] as int));
  final fee = lines.any((l) => l['available'] == true) ? 800 : 0;
  return {
    'lines': lines,
    'subtotalSen': sub,
    'deliveryFeeSen': fee,
    'grandTotalSen': sub + fee,
  };
}

Map<String, Object?> _product(String id, {int stock = 5}) => {
      'id': id,
      'name': 'Product $id',
      'category': {'id': 1, 'name': 'Cat'},
      'priceSen': 1000,
      'stock': {'status': 'in_stock', 'quantity': stock},
    };

CatalogueProduct _catalogue(String id, {int stock = 5}) =>
    CatalogueProduct.fromJson(_product(id, stock: stock));

Future<(ProviderContainer, SharedPreferences, List<String>)> _setup(
  SessionState session,
  Future<http.Response> Function(http.Request r) handler, {
  Map<String, int> local = const {},
}) async {
  SharedPreferences.setMockInitialValues(
      {if (local.isNotEmpty) legacyCartKey: jsonEncode(local)});
  final prefs = await SharedPreferences.getInstance();
  final calls = <String>[];
  final c = ProviderContainer(overrides: [
    sessionProvider.overrideWith(() => _FakeSession(session)),
    legacyLocalStoreProvider
        .overrideWith((ref) async => LegacyLocalStore(prefs)),
    apiClientProvider.overrideWithValue(ApiClient(
      baseUrl: 'http://t',
      client: MockClient((r) {
        calls.add('${r.method} ${r.url.path}');
        return handler(r);
      }),
      token: 'tok',
    )),
  ]);
  addTearDown(c.dispose);
  return (c, prefs, calls);
}

void main() {
  test('badge label is hidden for 0 and capped at 99+', () async {
    expect(badgeLabel(0), isNull);
    expect(badgeLabel(99), '99');
    expect(badgeLabel(100), '99+');
  });

  test('guest cart: add, limit of 20 and stock message', () async {
    final (c, prefs, _) = await _setup(const SessionSignedOut(), (r) async {
      if (r.url.path == '/api/products/a') {
        return _json(200, _product('a', stock: 3));
      }
      return _json(404, {});
    });
    expect((await c.read(cartProvider.future)).cart.lines, isEmpty);
    final n = c.read(cartProvider.notifier);
    final p = _catalogue('a', stock: 3);
    expect(await n.addProduct(p, null, quantity: 2), isNull);
    expect(await n.addProduct(p, null, quantity: 2), 'Only 3 available');
    expect(await n.addProduct(_catalogue('a', stock: 50), null, quantity: 20),
        'A single line can hold at most 20 units');
    final s = c.read(cartProvider).requireValue;
    expect(s.cart.itemCount, 2);
    expect(s.cart.subtotalSen, 2000);
    expect(s.cart.grandTotalSen, 2800);
    expect(c.read(cartBadgeProvider), '2');
    expect(jsonDecode(prefs.getString(legacyCartKey)!), {'a': 2});
  });

  test('guest cart flags a deleted product as unavailable', () async {
    final (c, _, _) = await _setup(const SessionSignedOut(), (r) async {
      return _json(404, {
        'error': {'code': 'not_found', 'message': 'gone'}
      });
    }, local: {'zzz': 2});
    final s = await c.read(cartProvider.future);
    expect(s.cart.lines.single.available, isFalse);
    expect(s.cart.grandTotalSen, 0);
    expect(s.cart.deliveryFeeSen, 0);
  });

  test('signed-in 409 shows the available quantity and leaves cart unchanged',
      () async {
    final (c, _, calls) = await _setup(_customer, (r) async {
      if (r.method == 'GET') return _json(200, _cart([_line('a', 1)]));
      return _json(409, {
        'error': {
          'code': 'insufficient_stock',
          'message': 'Only 2 available',
          'details': [
            {'productId': 'a', 'requested': 9, 'available': 2}
          ],
        }
      });
    });
    await c.read(cartProvider.future);
    final err = await c
        .read(cartProvider.notifier)
        .addProduct(_catalogue('a'), null, quantity: 8);
    expect(err, 'Only 2 available');
    expect(c.read(cartProvider).requireValue.cart.itemCount, 1);
    expect(calls, contains('POST /api/cart/lines'));
  });

  test('login merge keeps unmerged items locally and reports them', () async {
    final (c, prefs, _) = await _setup(_customer, (r) async {
      if (r.url.path == '/api/cart/merge') {
        return _json(200, {
          'cart': _cart([_line('a', 20)]),
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
    }, local: {'a': 20});
    final s = await c.read(cartProvider.future);
    expect(s.notMerged.single.quantity, 3);
    expect(s.notMerged.single.name, 'Product a');
    expect(jsonDecode(prefs.getString(legacyCartKey)!), {'a': 3});
  });

  test('successful merge clears the local cart; failed merge keeps it',
      () async {
    final (c, prefs, _) = await _setup(_customer, (r) async {
      if (r.url.path == '/api/cart/merge') {
        return _json(200, {
          'cart': _cart([_line('a', 2)]),
          'notMerged': []
        });
      }
      return _json(500, {});
    }, local: {'a': 2});
    final s = await c.read(cartProvider.future);
    expect(s.notMerged, isEmpty);
    expect(prefs.getString(legacyCartKey), isNull);

    final (c2, prefs2, _) = await _setup(_customer, (r) async {
      if (r.method == 'GET') return _json(200, _cart([]));
      return _json(500, {});
    }, local: {'a': 2});
    final s2 = await c2.read(cartProvider.future);
    expect(s2.mergePending, isTrue);
    expect(jsonDecode(prefs2.getString(legacyCartKey)!), {'a': 2});
  });

  testWidgets('cart screen shows empty state, unavailable flag and totals',
      (tester) async {
    var lines = <Map<String, Object?>>[];
    final (c, _, _) = await _setup(_customer, (r) async {
      return _json(200, _cart(lines));
    });
    Future<void> pump() async {
      await tester.pumpWidget(UncontrolledProviderScope(
          container: c, child: const MaterialApp(home: CartScreen())));
      await tester.pumpAndSettle();
    }

    await pump();
    expect(find.text('Your cart is empty.'), findsOneWidget);

    lines = [_line('a', 2), _line('b', 1, available: false, id: 2)];
    c.invalidate(cartProvider);
    await tester.pumpAndSettle();
    expect(find.textContaining('Unavailable'), findsOneWidget);
    expect(find.text('RM 20.00'), findsOneWidget); // subtotal
    expect(find.text('RM 8.00'), findsOneWidget); // delivery
    expect(find.text('RM 28.00'), findsOneWidget); // total
  });
}
