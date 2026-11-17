import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/storage/preferences_provider.dart';
import '../../../core/storage/token_store.dart';
import '../data/auth_user.dart';

/// Where the session stands (Req 5.5, 5.6, 5.11).
sealed class SessionState {
  const SessionState();
}

/// Start-up token validation is running.
class SessionChecking extends SessionState {
  const SessionChecking();
}

class SessionSignedOut extends SessionState {
  const SessionSignedOut();
}

class SessionSignedIn extends SessionState {
  const SessionSignedIn(this.user);

  final AuthUser user;

  AppRole get role => user.role;
}

/// Start-up validation got no answer. The stored token is kept (Req 5.11).
class SessionServerUnreachable extends SessionState {
  const SessionServerUnreachable([
    this.message = 'The server could not be reached',
  ]);

  final String message;
}

/// Owns the sign-in state. Validates a stored token at start-up with a 10 s
/// timeout, deletes the token on 401 and keeps it when the server is
/// unreachable.
class SessionNotifier extends Notifier<SessionState> {
  @override
  SessionState build() {
    // A 401 on any call clears the token (see apiClientProvider); follow it.
    ref.listen<AsyncValue<String?>>(authTokenProvider, (prev, next) {
      final cleared = next.hasValue && next.value == null;
      if (cleared && state is SessionSignedIn) {
        state = const SessionSignedOut();
      }
    });
    Future.microtask(validate);
    return const SessionChecking();
  }

  /// Validates the stored token and updates [state]. Also used as the
  /// "session refresh" that applies a changed role (Req 6.11).
  ///
  /// A returning user whose account was saved on this device is let into the
  /// app at once and the token is checked in the background, so a sleeping
  /// server never holds up the start screen. A 401 still signs them out.
  Future<void> validate() async {
    final String? token;
    try {
      token = await ref.read(authTokenProvider.future);
    } catch (_) {
      state = const SessionSignedOut();
      return;
    }
    if (token == null || token.isEmpty) {
      state = const SessionSignedOut();
      return;
    }
    final cached = await _cachedUser();
    if (cached != null && state is! SessionSignedIn) {
      state = SessionSignedIn(cached);
    }
    final client = ref.read(apiClientProvider);
    // A free-tier server sleeps when idle and takes up to a minute to wake,
    // so keep trying (each attempt still times out after 10 s) until the
    // wake-up budget is spent. Only then report it as unreachable.
    final deadline = DateTime.now().add(ref.read(serverWakeBudgetProvider));
    while (true) {
      try {
        final data = await client.get(
          '/api/auth/session',
          timeout: reachabilityTimeout,
          deleteTokenOn401: false,
        );
        final user = _userFrom(data);
        await _saveUser(user);
        // Only replace the state when something changed (e.g. a new role),
        // so screens are not rebuilt for nothing.
        final now = state;
        if (now is! SessionSignedIn || now.user != user) {
          state = SessionSignedIn(user);
        }
        return;
      } on UnauthorizedFailure {
        await ref.read(authTokenProvider.notifier).clear();
        await _saveUser(null);
        state = const SessionSignedOut();
        return;
      } catch (e) {
        // Network, timeout, 5xx: retry while the server may still be waking.
        if (DateTime.now().add(_retryPause).isBefore(deadline)) {
          await Future<void>.delayed(_retryPause);
          continue;
        }
        // Give up. A user let in from the saved account stays in; screens
        // that need the server show their own retry. Otherwise keep the
        // token and show the login screen.
        if (state is! SessionSignedIn) {
          state = SessionServerUnreachable(
              _unreachableMessage(e is AppFailure ? e : null, client.baseUrl));
        }
        return;
      }
    }
  }

  static const _retryPause = Duration(seconds: 2);

  /// Signs in. Throws an [AppFailure] on bad credentials, lockout or network
  /// problems and leaves the state unchanged.
  Future<AuthUser> login(String email, String password) async {
    final client = ref.read(apiClientProvider);
    final data = await client.post('/api/auth/login',
        body: {'email': email.trim(), 'password': password});
    final map = data as Map;
    final token = map['token']?.toString();
    if (token == null || token.isEmpty) {
      throw const ServerFailure(message: 'Unexpected response');
    }
    final user = AuthUser.fromJson(
      Map<String, dynamic>.from(map['user'] as Map),
      role: map['role']?.toString(),
    );
    await ref.read(authTokenProvider.notifier).setToken(token);
    await _saveUser(user);
    state = SessionSignedIn(user);
    return user;
  }

  static const _userKey = 'sagemaker_session_user_v1';

  /// The account saved on this device at the last sign-in or check, or null.
  Future<AuthUser?> _cachedUser() async {
    try {
      final prefs = await ref.read(sharedPreferencesProvider.future);
      final raw = prefs?.getString(_userKey);
      if (raw == null) return null;
      final map = Map<String, dynamic>.from(jsonDecode(raw) as Map);
      final user = AuthUser.fromJson(map);
      return user.id > 0 ? user : null;
    } catch (_) {
      return null; // unreadable: fall back to waiting for the server
    }
  }

  /// Saves (or with null, forgets) the signed-in account: id, name, email
  /// and role only. The token stays in its own store.
  Future<void> _saveUser(AuthUser? user) async {
    try {
      final prefs = await ref.read(sharedPreferencesProvider.future);
      if (prefs == null) return;
      if (user == null) {
        await prefs.remove(_userKey);
      } else {
        await prefs.setString(
            _userKey,
            jsonEncode({
              'id': user.id,
              'name': user.name,
              'email': user.email,
              'role': user.role.name,
            }));
      }
    } catch (_) {
      // Storage blocked: the app still works, it just waits at start-up.
    }
  }

  /// Revokes the token on a best-effort basis and always signs out locally.
  Future<void> logout() async {
    final client = ref.read(apiClientProvider);
    if (client.token != null) {
      try {
        await client.post('/api/auth/logout');
      } catch (_) {
        // The local sign-out must not depend on the network.
      }
    }
    await ref.read(authTokenProvider.notifier).clear();
    await _saveUser(null);
    state = const SessionSignedOut();
  }

  AuthUser _userFrom(dynamic data) {
    final map = Map<String, dynamic>.from(data as Map);
    return AuthUser.fromJson(
      Map<String, dynamic>.from(map['user'] as Map),
      role: map['role']?.toString(),
    );
  }

  String _unreachableMessage(AppFailure? e, String baseUrl) {
    if (e is ServerFailure) return 'The server returned an error ($baseUrl)';
    return 'The server could not be reached ($baseUrl). '
        'Check your internet connection and sign in to try again.';
  }
}

final sessionProvider =
    NotifierProvider<SessionNotifier, SessionState>(SessionNotifier.new);

/// How long start-up keeps retrying the server. Render's free tier needs 30
/// to 60 s to wake from sleep; tests set this to zero.
final serverWakeBudgetProvider =
    Provider<Duration>((ref) => const Duration(seconds: 75));
