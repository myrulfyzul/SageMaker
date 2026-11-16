import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/app/navigation_memory.dart';
import 'package:sagemaker_flutter/app/role_permissions.dart';
import 'package:sagemaker_flutter/app/router.dart';
import 'package:sagemaker_flutter/app/shells/customer_shell.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/token_store.dart';
import 'package:sagemaker_flutter/features/admin/production/state/production_provider.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';

const _customer =
    AuthUser(id: 1, name: 'C', email: 'c@x.my', role: AppRole.customer);
const _admin = AuthUser(id: 2, name: 'A', email: 'a@x.my', role: AppRole.admin);
const _artisan =
    AuthUser(id: 3, name: 'R', email: 'r@x.my', role: AppRole.artisan);

class _FakeSession extends SessionNotifier {
  _FakeSession(this.initial);
  final SessionState initial;

  @override
  SessionState build() => initial;
}

http.Response _json(Object body, [int status = 200]) =>
    http.Response(jsonEncode(body), status,
        headers: {'content-type': 'application/json'});

ProviderContainer _container({
  required http.Client Function() client,
  String? token,
  TokenStore? store,
}) {
  final tokens = store ?? MemoryTokenStore(token);
  final c = ProviderContainer(overrides: [
    tokenStoreProvider.overrideWithValue(tokens),
    apiClientProvider.overrideWith((ref) {
      final t = ref.watch(authTokenProvider).value;
      return ApiClient(
        baseUrl: 'http://test',
        token: t,
        client: client(),
        onUnauthorized: () => ref.read(authTokenProvider.notifier).clear(),
      );
    }),
  ]);
  addTearDown(c.dispose);
  return c;
}

Future<SessionState> _settle(ProviderContainer c) async {
  c.listen(sessionProvider, (_, __) {});
  for (var i = 0; i < 50; i++) {
    await Future<void>.delayed(Duration.zero);
    if (c.read(sessionProvider) is! SessionChecking) break;
  }
  return c.read(sessionProvider);
}

Map<String, dynamic> _sessionBody(AuthUser u) => {
      'user': {
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'role': u.role.name
      },
      'role': u.role.name,
      'expiresAt': '2099-01-01T00:00:00Z',
    };

void main() {
  group('sessionProvider', () {
    test('no stored token -> signedOut', () async {
      final c = _container(client: () => MockClient((_) async => _json({})));
      expect(await _settle(c), isA<SessionSignedOut>());
    });

    test('valid token -> signedIn with role', () async {
      final c = _container(
        token: 't',
        client: () => MockClient((r) async {
          expect(r.headers['Authorization'], 'Bearer t');
          return _json(_sessionBody(_admin));
        }),
      );
      final s = await _settle(c);
      expect(s, isA<SessionSignedIn>());
      expect((s as SessionSignedIn).role, AppRole.admin);
    });

    test('401 deletes the stored token (Req 5.6)', () async {
      final store = MemoryTokenStore('old');
      final c = _container(
        store: store,
        client: () => MockClient((_) async => _json({
              'error': {'code': 'session_expired'}
            }, 401)),
      );
      expect(await _settle(c), isA<SessionSignedOut>());
      expect(await store.read(), isNull);
    });

    test('unreachable keeps the token (Req 5.11)', () async {
      final store = MemoryTokenStore('keep');
      final c = _container(
        store: store,
        client: () =>
            MockClient((_) async => throw http.ClientException('down')),
      );
      final s = await _settle(c);
      expect(s, isA<SessionServerUnreachable>());
      expect(await store.read(), 'keep');
    });

    test('login stores token and logout clears it', () async {
      final store = MemoryTokenStore();
      final c = _container(
        store: store,
        client: () => MockClient((r) async {
          if (r.url.path == '/api/auth/login') {
            return _json({
              'token': 'tok',
              'expiresAt': 'x',
              'role': 'customer',
              'user': {
                'id': 1,
                'name': 'C',
                'email': 'c@x.my',
                'role': 'customer'
              },
            });
          }
          if (r.url.path == '/api/auth/logout') return http.Response('', 204);
          return _json({});
        }),
      );
      await _settle(c);
      await c.read(sessionProvider.notifier).login('c@x.my', 'pw');
      expect(c.read(sessionProvider), isA<SessionSignedIn>());
      expect(await store.read(), 'tok');
      await c.read(sessionProvider.notifier).logout();
      expect(c.read(sessionProvider), isA<SessionSignedOut>());
      expect(await store.read(), isNull);
    });
  });

  group('RolePermissions', () {
    test('seller and admin see five destinations in order', () {
      for (final r in [AppRole.seller, AppRole.admin]) {
        expect(RolePermissions.staffDestinationsFor(r).map((d) => d.label),
            ['Dashboard', 'Orders', 'Products', 'Production', 'More']);
        expect(RolePermissions.moreItemsFor(r).map((m) => m.label), [
          'Inventory',
          'Artisans',
          'Analytics',
          'Forecasting',
          'Notifications',
          'Settings'
        ]);
      }
    });

    test('artisan sees Production only', () {
      expect(RolePermissions.staffDestinationsFor(AppRole.artisan),
          [StaffDestination.production]);
      expect(RolePermissions.canOpenStaffPath(AppRole.artisan, '/staff/orders'),
          isFalse);
      expect(
          RolePermissions.canOpenStaffPath(
              AppRole.artisan, '/staff/production'),
          isTrue);
      expect(
          RolePermissions.canOpenStaffPath(
              AppRole.customer, '/staff/production'),
          isFalse);
    });
  });

  group('resolveRedirect', () {
    Uri u(String s) => Uri.parse(s);

    test('checking goes to splash', () {
      expect(resolveRedirect(const SessionChecking(), u('/shop')), '/splash');
      expect(resolveRedirect(const SessionChecking(), u('/splash')), isNull);
    });

    test('signed out: guarded paths go to login with from (Req 18.7)', () {
      for (final p in [
        '/favourites',
        '/profile',
        '/orders',
        '/checkout',
        '/staff/orders'
      ]) {
        final r = resolveRedirect(const SessionSignedOut(), u(p))!;
        expect(Uri.parse(r).path, '/login');
        expect(Uri.parse(r).queryParameters['from'], p);
      }
      expect(resolveRedirect(const SessionSignedOut(), u('/')), isNull);
      expect(resolveRedirect(const SessionSignedOut(), u('/cart')), isNull);
      expect(resolveRedirect(const SessionSignedOut(), u('/splash')), '/');
    });

    test('unreachable at splash goes to login', () {
      expect(resolveRedirect(const SessionServerUnreachable(), u('/splash')),
          '/login');
    });

    test('signed in customer returns to from after login', () {
      const s = SessionSignedIn(_customer);
      expect(resolveRedirect(s, u('/login?from=%2Fprofile')), '/profile');
      expect(resolveRedirect(s, u('/login')), '/');
      expect(resolveRedirect(s, u('/login?from=%2Fstaff%2Forders')), '/');
      expect(resolveRedirect(s, u('/login?from=%2F%2Fevil.com')), '/');
      expect(resolveRedirect(s, u('/staff/orders')), '/');
    });

    test('staff are kept in the staff area', () {
      const admin = SessionSignedIn(_admin);
      expect(resolveRedirect(admin, u('/login')), '/staff/dashboard');
      expect(resolveRedirect(admin, u('/shop')), '/staff/dashboard');
      expect(resolveRedirect(admin, u('/staff/more/inventory')), isNull);
      expect(resolveRedirect(admin, u('/about')), isNull);
      const art = SessionSignedIn(_artisan);
      expect(resolveRedirect(art, u('/login')), '/staff/production');
      expect(resolveRedirect(art, u('/staff/orders')), '/staff/production');
      expect(resolveRedirect(art, u('/staff/production')), isNull);
    });
  });

  group('router and shells', () {
    Future<(GoRouter, ProviderContainer)> pump(
        WidgetTester tester, SessionState session,
        {int cart = 0}) async {
      final container = ProviderContainer(overrides: [
        sessionProvider.overrideWith(() => _FakeSession(session)),
        cartItemCountProvider.overrideWith((ref) => cart),
        // The Production tab loads real jobs; keep the router test offline.
        productionJobsProvider.overrideWith((ref) async => const []),
      ]);
      addTearDown(container.dispose);
      final router = container.read(routerProvider);
      await tester.pumpWidget(UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(theme: buildAppTheme(), routerConfig: router),
      ));
      await tester.pumpAndSettle();
      return (router, container);
    }

    testWidgets('customer shell has five destinations and cart badge 99+',
        (tester) async {
      await pump(tester, const SessionSignedOut(), cart: 120);
      final bar = tester.widget<NavigationBar>(find.byType(NavigationBar));
      expect(bar.destinations.length, 5);
      for (final l in ['Home', 'Shop', 'Favourites', 'Cart', 'Profile']) {
        expect(find.text(l), findsWidgets);
      }
      expect(find.text('99+'), findsOneWidget);
    });

    testWidgets('signed-out Favourites opens login; cancel returns',
        (tester) async {
      final (router, _) = await pump(tester, const SessionSignedOut());
      await tester.tap(find.text('Shop').last);
      await tester.pumpAndSettle();
      expect(find.text('Shop'), findsWidgets);

      await tester.tap(find.text('Favourites'));
      await tester.pumpAndSettle();
      expect(router.state.uri.path, '/login');
      expect(router.state.uri.queryParameters['from'], '/favourites');

      await tester.tap(find.byTooltip('Cancel'));
      await tester.pumpAndSettle();
      expect(router.state.uri.path, '/shop');
      expect(find.byType(NavigationBar), findsOneWidget);
    });

    testWidgets('admin gets five staff tabs; artisan gets no bar',
        (tester) async {
      await pump(tester, const SessionSignedIn(_admin));
      expect(find.byType(NavigationBar), findsOneWidget);
      expect(
          tester
              .widget<NavigationBar>(find.byType(NavigationBar))
              .destinations
              .length,
          5);
      await tester.tap(find.text('More').last);
      await tester.pumpAndSettle();
      expect(find.text('Forecasting'), findsOneWidget);
    });

    testWidgets('artisan sees Production only', (tester) async {
      final (router, _) = await pump(tester, const SessionSignedIn(_artisan));
      expect(router.state.uri.path, '/staff/production');
      expect(find.byType(NavigationBar), findsNothing);
    });

    testWidgets('sign-out switches navigation to customer', (tester) async {
      final (router, container) =
          await pump(tester, const SessionSignedIn(_admin));
      expect(router.state.uri.path, '/staff/dashboard');
      container.read(sessionProvider.notifier).state = const SessionSignedOut();
      await tester.pumpAndSettle();
      expect(router.state.uri.path, '/');
      expect(
          tester
              .widget<NavigationBar>(find.byType(NavigationBar))
              .destinations
              .first,
          isA<NavigationDestination>().having((d) => d.label, 'label', 'Home'));
    });
  });

  test('NavigationMemory defaults to home', () {
    expect(NavigationMemory().lastAllowed, '/');
  });
}
