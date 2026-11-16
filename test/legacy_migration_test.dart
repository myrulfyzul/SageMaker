import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:sagemaker_flutter/core/money.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/legacy_local_store.dart';
import 'package:sagemaker_flutter/features/cart/data/guest_cart_repository.dart';
import 'package:sagemaker_flutter/features/cart/state/cart_store.dart';
import 'package:sagemaker_flutter/features/catalogue/data/product.dart';
import 'package:sagemaker_flutter/features/catalogue/data/product_repository.dart';
import 'package:sagemaker_flutter/features/favourites/data/local_favourites_repository.dart';
import 'package:sagemaker_flutter/features/favourites/state/favourites_store.dart';
import 'package:sagemaker_flutter/features/orders/data/legacy_orders_repository.dart';
import 'package:sagemaker_flutter/features/orders/state/orders_store.dart';

Future<LegacyLocalStore> storeWith(Map<String, Object> values) async {
  SharedPreferences.setMockInitialValues(values);
  return LegacyLocalStore(await SharedPreferences.getInstance());
}

ApiClient clientFor(MockClient mock) =>
    ApiClient(baseUrl: 'http://api.test', client: mock);

void main() {
  test('formatRm keeps the old money() output', () {
    expect(formatRm(3500), 'RM 35.00');
    expect(formatRm(0), 'RM 0.00');
    expect(formatRm(805), 'RM 8.05');
  });

  group('guest cart (key sagemaker_demo_cart_v1)', () {
    test('reads old data and clamps quantities to 1-20', () async {
      final store = await storeWith({
        'sagemaker_demo_cart_v1': jsonEncode({'a': 3, 'b': 99, 'c': 0}),
      });
      final cart = CartStore(GuestCartRepository(store));
      expect(cart.quantity('a'), 3);
      expect(cart.quantity('b'), 20);
      expect(cart.quantity('c'), 0);
      expect(cart.count, 23);
    });

    test('setQuantity clamps, add increments, 0 removes, and persists', () async {
      final store = await storeWith({});
      final cart = CartStore(GuestCartRepository(store));
      await cart.setQuantity('a', 50);
      expect(cart.quantity('a'), 20);
      await cart.add('a');
      expect(cart.quantity('a'), 20);
      await cart.setQuantity('b', 1);
      await cart.setQuantity('b', 0);
      expect(cart.quantity('b'), 0);
      final prefs = await SharedPreferences.getInstance();
      expect(jsonDecode(prefs.getString('sagemaker_demo_cart_v1')!), {'a': 20});
      await cart.clear();
      expect(cart.isEmpty, isTrue);
    });

    test('corrupt stored cart yields an empty cart', () async {
      final store = await storeWith({'sagemaker_demo_cart_v1': 'not json'});
      expect(CartStore(GuestCartRepository(store)).isEmpty, isTrue);
    });
  });

  group('local favourites (key sagemaker_saved_product_ids)', () {
    test('reads old ids, toggles and persists', () async {
      final store = await storeWith({
        'sagemaker_saved_product_ids': ['fishing', 'pouch'],
      });
      final favs = FavoritesStore(LocalFavouritesRepository(store));
      expect(favs.contains('fishing'), isTrue);
      await favs.toggle('fishing');
      await favs.toggle('hikayat');
      expect(favs.contains('fishing'), isFalse);
      expect(favs.count, 2);
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getStringList('sagemaker_saved_product_ids')!.toSet(),
          {'pouch', 'hikayat'});
    });

    test('clear removes the local copy', () async {
      final store = await storeWith({
        'sagemaker_saved_product_ids': ['a'],
      });
      await LocalFavouritesRepository(store).clear();
      expect(store.readFavouriteIds(), isEmpty);
    });
  });

  group('legacy orders (key sagemaker_demo_orders_v1)', () {
    test('lists old saved orders and adds newest first', () async {
      final store = await storeWith({
        'sagemaker_demo_orders_v1': jsonEncode([
          {'id': 'DEMO-1', 'token': 't1'},
        ]),
      });
      final client = clientFor(MockClient((_) async => http.Response('{}', 200)));
      final orders = OrdersStore(LegacyOrdersRepository(store, client));
      expect(orders.saved, [const SavedOrder('DEMO-1', 't1')]);
      await orders.add(const SavedOrder('DEMO-2', 't2'));
      expect(orders.saved.map((o) => o.id), ['DEMO-2', 'DEMO-1']);
      expect(store.readOrders().map((o) => o.id), ['DEMO-2', 'DEMO-1']);
    });

    test('tracks through /api/legacy/orders with the X-Order-Token', () async {
      final store = await storeWith({});
      late http.Request seen;
      final client = clientFor(MockClient((r) async {
        seen = r;
        return http.Response(jsonEncode({'id': 'DEMO-1', 'status': 'placed'}), 200);
      }));
      final repo = LegacyOrdersRepository(store, client);
      final info = await repo.getOrder(const SavedOrder('DEMO-1', 'tok'));
      expect(info['status'], 'placed');
      expect(seen.url.path, '/api/legacy/orders/DEMO-1');
      expect(seen.headers['X-Order-Token'], 'tok');
    });
  });

  group('products', () {
    test('Product.fromJson accepts priceSen or demoPriceSen', () {
      final legacy = Product.fromJson({
        'id': 'x', 'name': 'N', 'category': 'Kids & Toys', 'description': 'd',
        'imageUrl': 'i', 'productUrl': 'p', 'demoPriceSen': 3500,
      });
      expect(legacy.priceSen, 3500);
      expect(legacy.category, 'Kids & Toys');
      final modern = Product.fromJson({
        'id': 7, 'name': 'N', 'description': 'd', 'priceSen': 4900,
        'category': {'id': 1, 'slug': 'toys', 'name': 'Toys'},
        'images': [{'id': 1, 'url': 'u'}],
      });
      expect(modern.id, '7');
      expect(modern.priceSen, 4900);
      expect(modern.category, 'Toys');
      expect(modern.imageUrl, 'u');
    });

    const bundled = '[{"id":"b","name":"Bundled","category":"c","description":"d",'
        '"imageUrl":"i","productUrl":"p","demoPriceSen":100}]';

    test('uses the server list (bare or paged) when available', () async {
      for (final body in [
        '[{"id":"s","name":"S","priceSen":200}]',
        '{"items":[{"id":"s","name":"S","priceSen":200}],"total":1}',
      ]) {
        final repo = ProductRepository(
          client: clientFor(MockClient((_) async => http.Response(body, 200))),
          loadAsset: (_) async => bundled,
        );
        final list = await repo.loadProducts();
        expect(list.single.id, 's');
        expect(list.single.priceSen, 200);
      }
    });

    test('falls back to the bundled JSON when the server fails', () async {
      for (final mock in [
        MockClient((_) async => throw http.ClientException('down')),
        MockClient((_) async => http.Response('oops', 500)),
      ]) {
        final repo = ProductRepository(
            client: clientFor(mock), loadAsset: (_) async => bundled);
        final list = await repo.loadProducts();
        expect(list.single.name, 'Bundled');
        expect(list.single.priceSen, 100);
      }
    });

    test('the shipped assets/products.json parses', () {
      final raw = File('assets/products.json').readAsStringSync();
      final list = ProductRepository.parse(jsonDecode(raw) as List<dynamic>);
      expect(list, isNotEmpty);
      expect(list.every((p) => p.priceSen > 0), isTrue);
    });
  });
}
