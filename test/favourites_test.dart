import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/legacy_local_store.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/catalogue/data/product.dart';
import 'package:sagemaker_flutter/features/catalogue/state/catalogue_provider.dart';
import 'package:sagemaker_flutter/features/favourites/state/favourites_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeSession extends SessionNotifier {
  _FakeSession(this.initial);
  final SessionState initial;
  @override
  SessionState build() => initial;
}

Map<String, Object?> _p(String id) => {
      'id': id,
      'name': 'Product $id',
      'category': {'name': 'Cat'},
      'priceSen': 1000,
    };

http.Response _json(int s, Object b) =>
    http.Response(jsonEncode(b), s, headers: {'content-type': 'application/json'});

const _customer = SessionSignedIn(
    AuthUser(id: 1, name: 'C', email: 'c@x.my', role: AppRole.customer));

Future<(ProviderContainer, SharedPreferences, List<String>)> _setup(
  SessionState session,
  Future<http.Response> Function(http.Request r) handler, {
  List<String> local = const [],
}) async {
  SharedPreferences.setMockInitialValues(
      {if (local.isNotEmpty) legacyFavouritesKey: local});
  final prefs = await SharedPreferences.getInstance();
  final calls = <String>[];
  final c = ProviderContainer(overrides: [
    sessionProvider.overrideWith(() => _FakeSession(session)),
    legacyLocalStoreProvider.overrideWith((ref) async => LegacyLocalStore(prefs)),
    apiClientProvider.overrideWithValue(ApiClient(
      baseUrl: 'http://t',
      client: MockClient((r) {
        calls.add('${r.method} ${r.url.path}');
        return handler(r);
      }),
      token: 'tok',
    )),
    productsProvider.overrideWith((ref) async => [
          Product.fromJson(_p('a')),
          Product.fromJson(_p('b')),
        ]),
  ]);
  addTearDown(c.dispose);
  return (c, prefs, calls);
}

void main() {
  test('guest sees local favourites and toggles them locally', () async {
    final (c, prefs, calls) =
        await _setup(const SessionSignedOut(), (_) async => _json(500, {}), local: ['a']);
    final s = await c.read(favouritesProvider.future);
    expect(s.ids, {'a'});
    expect(s.signedIn, isFalse);
    await c.read(favouritesProvider.notifier).toggle(Product.fromJson(_p('b')));
    expect(prefs.getStringList(legacyFavouritesKey)!.toSet(), {'a', 'b'});
    expect(calls, isEmpty);
  });

  test('first sign-in merges and clears local copy only after success', () async {
    final (c, prefs, calls) = await _setup(_customer, (r) async {
      expect(jsonDecode(r.body), {'productIds': ['a']});
      return _json(200, {'items': [_p('a'), _p('z')], 'total': 2});
    }, local: ['a']);
    final s = await c.read(favouritesProvider.future);
    expect(calls, ['POST /api/favourites/merge']);
    expect(s.ids, {'a', 'z'});
    expect(s.mergePending, isFalse);
    expect(prefs.getStringList(legacyFavouritesKey), isNull);
  });

  test('failed merge retains local copy, then retry succeeds', () async {
    var failMerge = true;
    final (c, prefs, calls) = await _setup(_customer, (r) async {
      if (r.url.path.endsWith('/merge')) {
        return failMerge ? _json(500, {}) : _json(200, {'items': [_p('a')], 'total': 1});
      }
      return _json(200, {'items': [_p('z')], 'total': 1});
    }, local: ['a']);
    final s = await c.read(favouritesProvider.future);
    expect(s.mergePending, isTrue);
    expect(s.ids, {'z'});
    expect(prefs.getStringList(legacyFavouritesKey), ['a']);
    failMerge = false;
    c.read(favouritesProvider.notifier).retry();
    await c.read(favouritesProvider.future);
    final r = c.read(favouritesProvider).requireValue;
    expect(r.mergePending, isFalse);
    expect(prefs.getStringList(legacyFavouritesKey), isNull);
    expect(calls.where((x) => x.contains('merge')).length, 2);
  });

  test('load failure surfaces an error that retry can recover from', () async {
    var ok = false;
    final (c, _, _) = await _setup(_customer, (r) async =>
        ok ? _json(200, {'items': [_p('a')], 'total': 1}) : _json(500, {}));
    await expectLater(c.read(favouritesProvider.future), throwsA(anything));
    ok = true;
    c.read(favouritesProvider.notifier).retry();
    await c.read(favouritesProvider.future);
    expect(c.read(favouritesProvider).requireValue.ids, {'a'});
  });

  test('signed-in toggle calls PUT/DELETE and failure leaves list unchanged', () async {
    var fail = false;
    final (c, _, calls) = await _setup(_customer, (r) async {
      if (r.method == 'GET') return _json(200, {'items': [_p('a')], 'total': 1});
      return fail ? _json(409, {'error': {'code': 'product_unavailable'}}) : http.Response('', 204);
    });
    await c.read(favouritesProvider.future);
    final n = c.read(favouritesProvider.notifier);
    await n.toggle(Product.fromJson(_p('a')));
    expect(c.read(favouritesProvider).requireValue.ids, isEmpty);
    fail = true;
    await expectLater(n.toggle(Product.fromJson(_p('b'))), throwsA(anything));
    expect(c.read(favouritesProvider).requireValue.ids, isEmpty);
    expect(calls, ['GET /api/favourites', 'DELETE /api/favourites/a', 'PUT /api/favourites/b']);
  });
}

