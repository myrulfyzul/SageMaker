import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
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
    final client = ref.read(apiClientProvider);
    try {
      final data = await client.get(
        '/api/auth/session',
        timeout: reachabilityTimeout,
        deleteTokenOn401: false,
      );
      state = SessionSignedIn(_userFrom(data));
    } on UnauthorizedFailure {
      await ref.read(authTokenProvider.notifier).clear();
      state = const SessionSignedOut();
    } on AppFailure catch (e) {
      // Network, timeout, 5xx: keep the token, show the login screen.
      state = SessionServerUnreachable(_unreachableMessage(e, client.baseUrl));
    } catch (_) {
      state = SessionServerUnreachable(
          _unreachableMessage(null, client.baseUrl));
    }
  }

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
    state = SessionSignedIn(user);
    return user;
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
    return 'The server could not be reached ($baseUrl)';
  }
}

final sessionProvider =
    NotifierProvider<SessionNotifier, SessionState>(SessionNotifier.new);
