import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../storage/preferences_provider.dart';

/// Compile-time default (`--dart-define API_BASE_URL=...`).
const apiBaseUrlDefine = String.fromEnvironment('API_BASE_URL');

const apiBaseUrlPrefsKey = 'sagemaker_api_base_url_override';
const maxApiBaseUrlLength = 2048;

const _androidDefault = 'http://10.0.2.2:8000';
const _otherDefault = 'http://localhost:8000';

/// Platform default: Android emulator host alias, otherwise localhost.
String platformDefaultBaseUrl({bool? isWeb, TargetPlatform? platform}) {
  final web = isWeb ?? kIsWeb;
  final p = platform ?? defaultTargetPlatform;
  return (!web && p == TargetPlatform.android) ? _androidDefault : _otherDefault;
}

/// Accepts only absolute http/https URLs with a host, at most 2048 chars.
bool isValidApiBaseUrl(String? value) {
  if (value == null || value.isEmpty || value.length > maxApiBaseUrlLength) {
    return false;
  }
  final uri = Uri.tryParse(value);
  if (uri == null || !uri.isAbsolute) return false;
  return (uri.scheme == 'http' || uri.scheme == 'https') && uri.host.isNotEmpty;
}

/// Override, else non-empty define, else platform default. Trailing slashes
/// are removed so paths can be appended.
String resolveApiBaseUrl({
  String? override,
  String define = '',
  required String platformDefault,
}) {
  final raw = (override != null && override.isNotEmpty)
      ? override
      : (define.isNotEmpty ? define : platformDefault);
  return _stripSlashes(raw);
}

String _stripSlashes(String s) {
  var end = s.length;
  while (end > 0 && s[end - 1] == '/') {
    end--;
  }
  return s.substring(0, end);
}

/// Thrown by [ApiConfigNotifier.saveOverride] for an invalid URL.
class InvalidApiBaseUrl implements Exception {
  const InvalidApiBaseUrl();

  @override
  String toString() => 'The value is not a valid URL';
}

/// Holds the API_Base_URL in use. State is the resolved URL.
class ApiConfigNotifier extends AsyncNotifier<String> {
  /// Overridable in tests.
  String get define => apiBaseUrlDefine;
  String get platformDefault => platformDefaultBaseUrl();

  @override
  Future<String> build() async {
    final prefs = await ref.watch(sharedPreferencesProvider.future);
    String? override;
    try {
      override = prefs?.getString(apiBaseUrlPrefsKey);
    } catch (_) {}
    if (!isValidApiBaseUrl(override)) override = null;
    return resolveApiBaseUrl(
      override: override,
      define: define,
      platformDefault: platformDefault,
    );
  }

  /// Validates and persists an override. On failure throws
  /// [InvalidApiBaseUrl] and keeps the previous value.
  Future<void> saveOverride(String value) async {
    final v = value.trim();
    if (!isValidApiBaseUrl(v)) throw const InvalidApiBaseUrl();
    state = AsyncData(_stripSlashes(v));
    try {
      final prefs = await ref.read(sharedPreferencesProvider.future);
      await prefs?.setString(apiBaseUrlPrefsKey, v);
    } catch (_) {
      // applies for this session even if storage is blocked
    }
  }

  /// Removes the override and reverts to define / platform default.
  Future<void> clearOverride() async {
    try {
      final prefs = await ref.read(sharedPreferencesProvider.future);
      await prefs?.remove(apiBaseUrlPrefsKey);
    } catch (_) {}
    state = AsyncData(resolveApiBaseUrl(
      define: define,
      platformDefault: platformDefault,
    ));
  }
}

final apiConfigProvider =
    AsyncNotifierProvider<ApiConfigNotifier, String>(ApiConfigNotifier.new);
