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
import 'package:sagemaker_flutter/features/auth/state/auth_actions.dart';
import 'package:sagemaker_flutter/features/auth/ui/login_screen.dart';
import 'package:sagemaker_flutter/features/auth/ui/register_screen.dart';
import 'package:sagemaker_flutter/features/cart/data/guest_cart_repository.dart';
import 'package:sagemaker_flutter/features/favourites/data/local_favourites_repository.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(Object? body, [int status = 200]) =>
    http.Response(jsonEncode(body), status,
        headers: {'content-type': 'application/json'});

Future<ProviderContainer> _pump(
    WidgetTester tester, Future<http.Response> Function(http.Request) handler,
    {Widget screen = const LoginScreen()}) async {
  SharedPreferences.setMockInitialValues({});
  final c = ProviderContainer(overrides: [
    tokenStoreProvider.overrideWithValue(MemoryTokenStore()),
    apiClientProvider.overrideWith((ref) => ApiClient(
          baseUrl: 'http://test',
          token: ref.watch(authTokenProvider).value,
          client: MockClient(handler),
        )),
  ]);
  addTearDown(c.dispose);
  await tester.pumpWidget(UncontrolledProviderScope(
    container: c,
    child: MaterialApp(theme: buildAppTheme(), home: screen),
  ));
  await tester.pump();
  return c;
}

void main() {
  group('LoginScreen', () {
    testWidgets('shows the SageMaker brand without scrolling', (tester) async {
      await _pump(tester, (_) async => _json({}, 401));
      expect(find.text('SageMaker'), findsOneWidget);
      expect(find.textContaining('prototype'), findsNothing);
    });

    testWidgets('429 shows remaining seconds and disables sign in',
        (tester) async {
      await _pump(
          tester,
          (_) async => _json({
                'error': {'code': 'locked', 'retryAfterSeconds': 240}
              }, 429));
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Email'), 'a@b.my');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Password'), 'x');
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pump();
      await tester.pump();
      expect(find.textContaining('240 seconds'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed,
          isNull);
      await tester.pump(const Duration(seconds: 1));
      expect(find.textContaining('239 seconds'), findsOneWidget);
      // Let the countdown finish so no timer stays pending.
      await tester.pump(const Duration(seconds: 240));
    });

    testWidgets('401 shows the generic message', (tester) async {
      await _pump(
          tester,
          (_) async => _json({
                'error': {'code': 'bad'}
              }, 401));
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Email'), 'a@b.my');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Password'), 'x');
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pump();
      await tester.pump();
      expect(find.text('Email or password is incorrect'), findsOneWidget);
    });
  });

  group('RegisterScreen', () {
    testWidgets('welcome header visible and no fictional-data notice',
        (tester) async {
      await _pump(tester, (_) async => _json({}),
          screen: const RegisterScreen());
      expect(find.text('Join SageMaker'), findsOneWidget);
      expect(find.textContaining('fictional'), findsNothing);
    });

    testWidgets('local validation errors; 422 field errors shown',
        (tester) async {
      await _pump(
          tester,
          (_) async => _json({
                'error': {
                  'code': 'validation_error',
                  'details': [
                    {'field': 'email', 'reason': 'Email format is invalid'}
                  ]
                }
              }, 422),
          screen: const RegisterScreen());
      await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
      await tester.pump();
      expect(find.text('Name must be 1 to 100 characters'), findsOneWidget);
      expect(find.text('Password must be 8 to 128 characters'), findsOneWidget);

      await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Ann');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Email'), 'ann@x.my');
      await tester.enterText(
          find.widgetWithText(TextFormField, 'Password'), 'abcdefg1');
      await tester.tap(find.widgetWithText(FilledButton, 'Create account'));
      await tester.pump();
      await tester.pump();
      expect(find.text('Email format is invalid'), findsOneWidget);
    });
  });

  group('PostLoginSync', () {
    test('uploads favourites, merges cart, keeps unmerged lines', () async {
      SharedPreferences.setMockInitialValues({
        legacyFavouritesKey: ['a', 'b'],
        legacyCartKey: jsonEncode({'a': 2, 'b': 3}),
      });
      final store = LegacyLocalStore(await SharedPreferences.getInstance());
      final calls = <String>[];
      final client = ApiClient(
        baseUrl: 'http://test',
        client: MockClient((r) async {
          calls.add(r.url.path);
          if (r.url.path == '/api/cart/merge') {
            return _json({
              'notMerged': [
                {'productId': 'b', 'name': 'Tote', 'quantity': 1}
              ]
            });
          }
          return _json({});
        }),
      );
      final report = await PostLoginSync(client,
              LocalFavouritesRepository(store), GuestCartRepository(store))
          .run();
      expect(calls, ['/api/favourites/merge', '/api/cart/merge']);
      expect(store.readFavouriteIds(), isEmpty);
      expect(store.readCart(), {'b': 1});
      expect(report.notMerged, ['Tote']);
      expect(report.message, contains('Tote'));
    });

    test('failures keep local data and do not throw', () async {
      SharedPreferences.setMockInitialValues({
        legacyFavouritesKey: ['a'],
        legacyCartKey: jsonEncode({'a': 2}),
      });
      final store = LegacyLocalStore(await SharedPreferences.getInstance());
      final client = ApiClient(
          baseUrl: 'http://test',
          client: MockClient((_) async => _json({}, 500)));
      final report = await PostLoginSync(client,
              LocalFavouritesRepository(store), GuestCartRepository(store))
          .run();
      expect(report.favouritesFailed, isTrue);
      expect(report.cartFailed, isTrue);
      expect(store.readFavouriteIds(), ['a']);
      expect(store.readCart(), {'a': 2});
    });
  });
}
