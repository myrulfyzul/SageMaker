import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/widgets/loading_view.dart';
import '../features/auth/data/auth_user.dart';
import '../features/auth/state/session_provider.dart';
import 'feature_routes.dart';
import 'navigation_memory.dart';
import 'role_permissions.dart';
import 'shells/customer_shell.dart';
import 'shells/staff_shell.dart';

const _splash = '/splash';

/// Customer destinations that need a signed-in user (Req 18.7).
const _guardedPrefixes = [
  '/favourites',
  '/checkout',
  '/profile',
  '/orders',
  '/payment',
  '/confirmation',
  '/notifications',
  '/custom-orders',
  '/staff',
];

/// Open to every session, whatever the role.
const _sharedPaths = {'/welcome', '/about', '/settings/connection'};

bool _isGuarded(String path) =>
    _guardedPrefixes.any((p) => path == p || path.startsWith('$p/'));

bool _isAuthScreen(String path) => path == '/login' || path == '/register';

/// A `from` value is only followed if it is an in-app path that [role] may
/// open. Anything else falls back to the role's home.
String? safeReturnTarget(String? from, AppRole role) {
  if (from == null || !from.startsWith('/') || from.startsWith('//')) {
    return null;
  }
  final uri = Uri.tryParse(from);
  if (uri == null) return null;
  final path = uri.path;
  if (path == _splash || _isAuthScreen(path)) return null;
  if (role.isStaff) {
    return RolePermissions.canOpenStaffPath(role, path) && path != '/staff'
        ? from
        : null;
  }
  return path.startsWith('/staff') ? null : from;
}

/// Pure redirect rule. Returns the location to go to, or null to stay.
String? resolveRedirect(SessionState session, Uri uri) {
  final path = uri.path;

  switch (session) {
    case SessionChecking():
      return path == _splash ? null : _splash;

    case SessionSignedOut() || SessionServerUnreachable():
      // Signed-out launches open the SageMaker landing page first.
      if (path == _splash) {
        return session is SessionServerUnreachable ? '/login' : '/welcome';
      }
      if (_isGuarded(path)) {
        return Uri(path: '/login', queryParameters: {'from': uri.toString()})
            .toString();
      }
      return null;

    case SessionSignedIn(:final role):
      if (path == _splash || _isAuthScreen(path)) {
        return safeReturnTarget(uri.queryParameters['from'], role) ??
            RolePermissions.homePath(role);
      }
      if (role.isStaff) {
        if (path == '/staff') return RolePermissions.homePath(role);
        if (path.startsWith('/staff/')) {
          return RolePermissions.canOpenStaffPath(role, path)
              ? null
              : RolePermissions.homePath(role);
        }
        return _sharedPaths.contains(path)
            ? null
            : RolePermissions.homePath(role);
      }
      return path == '/staff' || path.startsWith('/staff/') ? '/' : null;
  }
}

/// Router with role redirect, `/login?from=` return and role shells.
final routerProvider = Provider<GoRouter>((ref) {
  final memory = ref.read(navigationMemoryProvider);
  final refresh = ValueNotifier<int>(0);
  late final GoRouter router;
  ref.listen<SessionState>(sessionProvider, (previous, next) {
    // Sign-out returns to the customer home instead of a login redirect.
    if (previous is SessionSignedIn && next is SessionSignedOut) {
      router.go('/');
    }
    // Role or sign-in change: re-run redirects at once (Req 6.11).
    refresh.value++;
  });
  ref.onDispose(refresh.dispose);

  router = GoRouter(
    initialLocation: _splash,
    refreshListenable: refresh,
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      final result = resolveRedirect(session, state.uri);
      if (result == null &&
          state.uri.path != _splash &&
          !_isAuthScreen(state.uri.path)) {
        memory.lastAllowed = state.uri.toString();
      }
      return result;
    },
    routes: [
      GoRoute(
        path: _splash,
        builder: (context, state) => const Scaffold(body: LoadingView()),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) =>
            CustomerShell(navigationShell: shell),
        branches: customerBranches(),
      ),
      ...customerRoutes(),
      ...publicRoutes(),
      // `/staff` itself always redirects (to the role's home or to login).
      GoRoute(path: '/staff', builder: (c, s) => const SizedBox()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => StaffShell(navigationShell: shell),
        branches: staffBranches(),
      ),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
