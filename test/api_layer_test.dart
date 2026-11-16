import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/config/api_config.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/network/app_failure.dart';
import 'package:sagemaker_flutter/core/storage/token_store.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(int status, Object body) => http.Response(
      jsonEncode(body),
      status,
      headers: {'content-type': 'application/json'},
    );

ApiClient _client(MockClient mock,
        {String? token,
        Future<void> Function()? onUnauthorized,
        Duration? timeout}) =>
    ApiClient(
      baseUrl: 'http://x.test',
      client: mock,
      token: token,
      onUnauthorized: onUnauthorized,
      timeout: timeout ?? requestTimeout,
    );

class _ThrowingTokenStore implements TokenStore {
  @override
  Future<String?> read() async => throw StateError('x');
  @override
  Future<void> write(String token) async => throw StateError('x');
  @override
  Future<void> delete() async => throw StateError('x');
}

void main() {
  group('URL validation and resolution', () {
    test('accepts and rejects per Req 2.3', () {
      expect(isValidApiBaseUrl('http://192.168.1.5:8000'), isTrue);
      expect(isValidApiBaseUrl('https://api.example.com'), isTrue);
      for (final bad in [
        '',
        'ftp://a.com',
        'example.com',
        '/relative',
        'http://',
        'http:///x',
        'javascript:alert(1)'
      ]) {
        expect(isValidApiBaseUrl(bad), isFalse, reason: bad);
      }
      final long = 'http://a.com/${'a' * 2040}';
      expect(long.length, greaterThan(2048));
      expect(isValidApiBaseUrl(long), isFalse);
      expect(isValidApiBaseUrl('http://a.com/${'a' * 2030}'), isTrue);
    });

    test('precedence: override > define > platform default', () {
      expect(
          resolveApiBaseUrl(
              override: 'http://o',
              define: 'http://d',
              platformDefault: 'http://p'),
          'http://o');
      expect(resolveApiBaseUrl(define: 'http://d', platformDefault: 'http://p'),
          'http://d');
      expect(resolveApiBaseUrl(platformDefault: 'http://p'), 'http://p');
      expect(
          resolveApiBaseUrl(override: 'http://o/', platformDefault: 'http://p'),
          'http://o');
    });

    test('platform defaults', () {
      expect(
          platformDefaultBaseUrl(isWeb: true, platform: TargetPlatform.android),
          'http://localhost:8000');
      expect(
          platformDefaultBaseUrl(
              isWeb: false, platform: TargetPlatform.android),
          'http://10.0.2.2:8000');
      expect(
          platformDefaultBaseUrl(
              isWeb: false, platform: TargetPlatform.windows),
          'http://localhost:8000');
    });
  });

  group('ApiConfigNotifier', () {
    Future<ProviderContainer> make(
        [Map<String, Object> initial = const {}]) async {
      SharedPreferences.setMockInitialValues(initial);
      final c = ProviderContainer();
      addTearDown(c.dispose);
      await c.read(apiConfigProvider.future);
      return c;
    }

    test(
        'saves valid override, rejects invalid and keeps previous, clears to revert',
        () async {
      final c = await make();
      final base = c.read(apiConfigProvider).value!;
      expect(base, platformDefaultBaseUrl());

      await c
          .read(apiConfigProvider.notifier)
          .saveOverride('http://192.168.0.9:8000');
      expect(c.read(apiConfigProvider).value, 'http://192.168.0.9:8000');

      await expectLater(c.read(apiConfigProvider.notifier).saveOverride('nope'),
          throwsA(isA<InvalidApiBaseUrl>()));
      expect(c.read(apiConfigProvider).value, 'http://192.168.0.9:8000');

      await c.read(apiConfigProvider.notifier).clearOverride();
      expect(c.read(apiConfigProvider).value, base);
      expect(
          (await SharedPreferences.getInstance()).getString(apiBaseUrlPrefsKey),
          isNull);
    });

    test('persisted override is loaded; invalid persisted value is ignored',
        () async {
      var c = await make({apiBaseUrlPrefsKey: 'https://saved.example.com'});
      expect(c.read(apiConfigProvider).value, 'https://saved.example.com');
      c = await make({apiBaseUrlPrefsKey: 'garbage'});
      expect(c.read(apiConfigProvider).value, platformDefaultBaseUrl());
    });

    test('apiClientProvider picks up a saved URL without restart', () async {
      final c = await make();
      await c.read(authTokenProvider.future);
      await c
          .read(apiConfigProvider.notifier)
          .saveOverride('http://new.test:1');
      expect(c.read(apiClientProvider).baseUrl, 'http://new.test:1');
    });
  });

  group('ApiClient', () {
    test('sends Bearer token and returns decoded JSON', () async {
      late http.BaseRequest seen;
      final api = _client(MockClient((req) async {
        seen = req;
        return _json(200, {'ok': true});
      }), token: 'abc');
      final r = await api.get('/api/health', query: {'a': 1, 'b': null});
      expect(r, {'ok': true});
      expect(seen.headers['Authorization'], 'Bearer abc');
      expect(seen.url.toString(), 'http://x.test/api/health?a=1');
    });

    test('no Authorization header without token; POST sends JSON body',
        () async {
      late http.Request seen;
      final api = _client(MockClient((req) async {
        seen = req;
        return _json(201, {'id': 1});
      }));
      await api.post('/api/x', body: {'k': 'v'});
      expect(seen.headers.containsKey('Authorization'), isFalse);
      expect(jsonDecode(seen.body), {'k': 'v'});
    });

    Future<Object?> failure(int status, Object body) async {
      final api = _client(MockClient((_) async => _json(status, body)));
      try {
        await api.get('/x');
      } on AppFailure catch (e) {
        return e;
      }
      return null;
    }

    test('maps status codes to failures', () async {
      expect(
          await failure(401, {
            'error': {'code': 'session_expired', 'message': 'm'}
          }),
          isA<UnauthorizedFailure>()
              .having((f) => f.code, 'code', 'session_expired'));
      expect(
          await failure(403, {
            'error': {'code': 'forbidden', 'message': 'm'}
          }),
          isA<ForbiddenFailure>());
      expect(
          await failure(404, {
            'error': {'code': 'not_found', 'message': 'm'}
          }),
          isA<NotFoundFailure>());
      expect(
          await failure(409, {
            'error': {
              'code': 'insufficient_stock',
              'message': 'm',
              'details': [
                {'productId': 'a', 'available': 2}
              ]
            }
          }),
          isA<ConflictFailure>()
              .having((f) => f.code, 'code', 'insufficient_stock')
              .having((f) => f.details.length, 'details', 1));
      expect(
          await failure(422, {
            'error': {
              'code': 'validation_error',
              'message': 'm',
              'details': [
                {'field': 'postcode', 'reason': 'must be exactly 5 digits'}
              ]
            }
          }),
          isA<ValidationFailure>().having((f) => f.fields['postcode'],
              'postcode', 'must be exactly 5 digits'));
      expect(
          await failure(503, {
            'error': {'code': 'busy', 'message': 'm'}
          }),
          isA<ServerFailure>().having((f) => f.statusCode, 'status', 503));
      expect(await failure(500, 'not an envelope'), isA<ServerFailure>());
    });

    test('socket errors map to NetworkFailure with base URL', () async {
      final api =
          _client(MockClient((_) async => throw http.ClientException('boom')));
      await expectLater(
          api.get('/x'),
          throwsA(isA<NetworkFailure>()
              .having((f) => f.baseUrl, 'baseUrl', 'http://x.test')));
    });

    test('slow responses map to TimeoutFailure', () async {
      final api = _client(MockClient((_) => Completer<http.Response>().future),
          timeout: const Duration(milliseconds: 50));
      await expectLater(api.get('/x'), throwsA(isA<TimeoutFailure>()));
      await expectLater(
          _client(MockClient((_) => Completer<http.Response>().future))
              .get('/x', timeout: const Duration(milliseconds: 50)),
          throwsA(isA<TimeoutFailure>()));
    });

    test(
        '401 calls onUnauthorized only when a token was sent and deletion not suppressed',
        () async {
      var calls = 0;
      Future<void> cb() async => calls++;
      final mock = MockClient((_) async => _json(401, {
            'error': {'code': 'unauthenticated', 'message': 'm'}
          }));

      await expectLater(_client(mock, token: 't', onUnauthorized: cb).get('/x'),
          throwsA(isA<UnauthorizedFailure>()));
      expect(calls, 1);

      await expectLater(_client(mock, onUnauthorized: cb).get('/x'),
          throwsA(isA<UnauthorizedFailure>()));
      expect(calls, 1);

      await expectLater(
          _client(mock, token: 't', onUnauthorized: cb)
              .get('/x', deleteTokenOn401: false),
          throwsA(isA<UnauthorizedFailure>()));
      expect(calls, 1);
    });

    test('timeouts constants match spec', () {
      expect(reachabilityTimeout, const Duration(seconds: 10));
      expect(requestTimeout, const Duration(seconds: 15));
    });
  });

  group('TokenStore', () {
    test('web/fallback path stores in shared_preferences', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final store = SecureTokenStore(
          fallback: PreferencesTokenStore(() async => prefs), useSecure: false);
      expect(await store.read(), isNull);
      await store.write('tok');
      expect(await store.read(), 'tok');
      expect(prefs.getString(sessionStoreSlot), 'tok');
      await store.delete();
      expect(await store.read(), isNull);
    });

    test('storage failures never throw', () async {
      final store =
          SecureTokenStore(fallback: _ThrowingTokenStore(), useSecure: false);
      expect(await store.read(), isNull);
      await store.write('t');
      await store.delete();
    });

    test('memory store round trip', () async {
      final s = MemoryTokenStore();
      await s.write('a');
      expect(await s.read(), 'a');
      await s.delete();
      expect(await s.read(), isNull);
    });
  });
}
