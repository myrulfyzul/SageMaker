import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'preferences_provider.dart';

const sessionStoreSlot = 'sagemaker_session_token';

/// Storage for the Session_Token.
abstract class TokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> delete();
}

/// Keeps the token in memory only (tests, or when all storage is blocked).
class MemoryTokenStore implements TokenStore {
  MemoryTokenStore([this._token]);

  String? _token;

  @override
  Future<String?> read() async => _token;

  @override
  Future<void> write(String token) async => _token = token;

  @override
  Future<void> delete() async => _token = null;
}

/// Token storage in `shared_preferences`.
class PreferencesTokenStore implements TokenStore {
  PreferencesTokenStore(this._load);

  final Future<SharedPreferences?> Function() _load;

  @override
  Future<String?> read() async => (await _load())?.getString(sessionStoreSlot);

  @override
  Future<void> write(String token) async {
    await (await _load())?.setString(sessionStoreSlot, token);
  }

  @override
  Future<void> delete() async {
    await (await _load())?.remove(sessionStoreSlot);
  }
}

/// Secure storage where available, `shared_preferences` on web or when the
/// secure store fails. Storage errors never throw out of this class.
class SecureTokenStore implements TokenStore {
  SecureTokenStore({
    required TokenStore fallback,
    FlutterSecureStorage? secure,
    bool? useSecure,
  })  : _fallback = fallback,
        _useSecure = useSecure ?? !kIsWeb,
        _secure = secure ?? const FlutterSecureStorage();

  final TokenStore _fallback;
  final FlutterSecureStorage _secure;
  final bool _useSecure;

  @override
  Future<String?> read() async {
    if (_useSecure) {
      try {
        final v = await _secure.read(key: sessionStoreSlot);
        if (v != null) return v;
      } catch (_) {
        // fall through to the fallback store
      }
    }
    return _safe<String?>(_fallback.read);
  }

  @override
  Future<void> write(String token) async {
    if (_useSecure) {
      try {
        await _secure.write(key: sessionStoreSlot, value: token);
        return;
      } catch (_) {
        // use the fallback store
      }
    }
    await _safe(() => _fallback.write(token));
  }

  @override
  Future<void> delete() async {
    if (_useSecure) {
      try {
        await _secure.delete(key: sessionStoreSlot);
      } catch (_) {}
    }
    await _safe(_fallback.delete);
  }

  Future<T?> _safe<T>(Future<T> Function() f) async {
    try {
      return await f();
    } catch (_) {
      return null;
    }
  }
}

final tokenStoreProvider = Provider<TokenStore>((ref) {
  return SecureTokenStore(
    fallback:
        PreferencesTokenStore(() => ref.read(sharedPreferencesProvider.future)),
  );
});

/// Current Session_Token held in memory and mirrored to the [TokenStore].
/// `AsyncData(null)` means signed out. [ApiClient] rebuilds when it changes.
class AuthTokenNotifier extends AsyncNotifier<String?> {
  @override
  Future<String?> build() => ref.read(tokenStoreProvider).read();

  Future<void> setToken(String token) async {
    state = AsyncData(token);
    await ref.read(tokenStoreProvider).write(token);
  }

  Future<void> clear() async {
    state = const AsyncData(null);
    await ref.read(tokenStoreProvider).delete();
  }
}

final authTokenProvider =
    AsyncNotifierProvider<AuthTokenNotifier, String?>(AuthTokenNotifier.new);
