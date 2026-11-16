import 'dart:async';
import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../storage/token_store.dart';
import 'app_failure.dart';

const reachabilityTimeout = Duration(seconds: 10);
const requestTimeout = Duration(seconds: 15);

/// HTTP client: Bearer token, timeouts and error mapping to [AppFailure].
/// Methods return the decoded JSON body (or null for an empty body) and throw
/// an [AppFailure] on any failure.
class ApiClient {
  ApiClient({
    required this.baseUrl,
    http.Client? client,
    this.token,
    this.onUnauthorized,
    this.timeout = requestTimeout,
  }) : _client = client ?? http.Client();

  final String baseUrl;
  final String? token;
  final Duration timeout;

  /// Called on a 401 for a request that carried a token (not for
  /// [checkReachable]/start-up validation with `deleteTokenOn401: false`).
  final Future<void> Function()? onUnauthorized;
  final http.Client _client;

  Uri uri(String path, [Map<String, dynamic>? query]) {
    final p = path.startsWith('/') ? path : '/$path';
    final q = <String, String>{};
    query?.forEach((k, v) {
      if (v != null) q[k] = v.toString();
    });
    return Uri.parse('$baseUrl$p')
        .replace(queryParameters: q.isEmpty ? null : q);
  }

  Map<String, String> _headers({bool json = false}) => {
        'Accept': 'application/json',
        if (json) 'Content-Type': 'application/json',
        if (token != null && token!.isNotEmpty)
          'Authorization': 'Bearer $token',
      };

  Future<dynamic> get(String path,
          {Map<String, dynamic>? query,
          Duration? timeout,
          bool deleteTokenOn401 = true,
          Map<String, String>? headers}) =>
      _send('GET', path,
          query: query,
          timeout: timeout,
          deleteTokenOn401: deleteTokenOn401,
          extraHeaders: headers);

  Future<dynamic> post(String path,
          {Object? body,
          Map<String, dynamic>? query,
          Map<String, String>? headers}) =>
      _send('POST', path, body: body, query: query, extraHeaders: headers);

  Future<dynamic> put(String path, {Object? body}) =>
      _send('PUT', path, body: body);

  Future<dynamic> patch(String path, {Object? body}) =>
      _send('PATCH', path, body: body);

  Future<dynamic> delete(String path, {Object? body}) =>
      _send('DELETE', path, body: body);

  /// Multipart upload. [fields] are text fields; [files] go in [fileField].
  Future<dynamic> postMultipart(
    String path, {
    Map<String, String> fields = const {},
    String fileField = 'images',
    List<http.MultipartFile> files = const [],
  }) {
    final request = http.MultipartRequest('POST', uri(path))
      ..headers.addAll(_headers())
      ..fields.addAll(fields)
      ..files.addAll(files);
    return _run(
        () async => http.Response.fromStream(await _client.send(request)),
        timeout,
        true);
  }

  /// Start-up reachability check against `/api/health` with a 10 s timeout.
  Future<void> checkReachable() =>
      get('/api/health', timeout: reachabilityTimeout, deleteTokenOn401: false);

  Future<dynamic> _send(
    String method,
    String path, {
    Object? body,
    Map<String, dynamic>? query,
    Map<String, String>? extraHeaders,
    Duration? timeout,
    bool deleteTokenOn401 = true,
  }) {
    final request = http.Request(method, uri(path, query))
      ..headers.addAll(_headers(json: body != null))
      ..headers.addAll(extraHeaders ?? const {});
    if (body != null) request.body = jsonEncode(body);
    return _run(
        () async => http.Response.fromStream(await _client.send(request)),
        timeout,
        deleteTokenOn401);
  }

  Future<dynamic> _run(
    Future<http.Response> Function() call,
    Duration? timeoutOverride,
    bool deleteTokenOn401,
  ) async {
    final limit = timeoutOverride ?? timeout;
    final http.Response response;
    try {
      response = await call().timeout(limit);
    } on TimeoutException {
      throw TimeoutFailure(baseUrl: baseUrl);
    } on AppFailure {
      rethrow;
    } catch (_) {
      throw NetworkFailure(baseUrl: baseUrl);
    }
    return _handle(response, deleteTokenOn401);
  }

  Future<dynamic> _handle(http.Response r, bool deleteTokenOn401) async {
    final status = r.statusCode;
    final decoded = _decode(r.bodyBytes);
    if (status >= 200 && status < 300) return decoded;

    final err = (decoded is Map && decoded['error'] is Map)
        ? Map<String, dynamic>.from(decoded['error'] as Map)
        : const <String, dynamic>{};
    final code = err['code'] is String ? err['code'] as String : null;
    final msg = err['message'] is String ? err['message'] as String : null;
    final details = err['details'] is List ? err['details'] as List : const [];

    if (status == 401) {
      if (deleteTokenOn401 && token != null) await onUnauthorized?.call();
      throw UnauthorizedFailure(
          code: code, message: msg ?? 'Please sign in again');
    }
    if (status == 403) throw ForbiddenFailure(message: msg ?? 'Not allowed');
    if (status == 404) throw NotFoundFailure(message: msg ?? 'Not found');
    if (status == 409) {
      throw ConflictFailure(
          code: code ?? 'conflict',
          details: details,
          message: msg ?? 'Conflict');
    }
    if (status == 429) {
      throw RateLimitedFailure(
          retryAfterSeconds: _retrySeconds(err, details, r.headers),
          message: msg ?? 'Too many attempts');
    }
    if (status == 422 || (status == 400 && code == 'validation_error')) {
      final fields = <String, String>{};
      for (final d in details) {
        if (d is Map && d['field'] != null) {
          fields[d['field'].toString()] = (d['reason'] ?? 'invalid').toString();
        }
      }
      throw ValidationFailure(
          fields: fields,
          message: msg ?? 'Please check the highlighted fields');
    }
    if (status >= 500) {
      throw ServerFailure(
          statusCode: status, code: code, message: msg ?? 'Server error');
    }
    throw ServerFailure(
        statusCode: status,
        code: code,
        message: msg ?? 'Unexpected response ($status)');
  }

  /// Remaining wait from the error body (several accepted spellings, also
  /// inside `details`) or the `Retry-After` header.
  int? _retrySeconds(
      Map<String, dynamic> err, List details, Map<String, String> headers) {
    int? asInt(dynamic v) =>
        v is num ? v.toInt() : (v is String ? int.tryParse(v) : null);
    const keys = [
      'retryAfterSeconds',
      'retry_after_seconds',
      'retryAfter',
      'retry_after'
    ];
    for (final k in keys) {
      final v = asInt(err[k]);
      if (v != null) return v;
    }
    for (final d in details) {
      if (d is Map) {
        for (final k in [...keys, 'seconds', 'remainingSeconds']) {
          final v = asInt(d[k]);
          if (v != null) return v;
        }
      }
    }
    return asInt(headers['retry-after']);
  }

  dynamic _decode(List<int> bytes) {
    if (bytes.isEmpty) return null;
    try {
      return jsonDecode(utf8.decode(bytes));
    } catch (_) {
      return null;
    }
  }

  void close() => _client.close();
}

/// Rebuilds when the base URL or the token changes, so a saved URL applies
/// without a restart.
final apiClientProvider = Provider<ApiClient>((ref) {
  final baseUrl = ref.watch(apiConfigProvider).value ??
      resolveApiBaseUrl(
          define: apiBaseUrlDefine, platformDefault: platformDefaultBaseUrl());
  final token = ref.watch(authTokenProvider).value;
  final client = ApiClient(
    baseUrl: baseUrl,
    token: token,
    onUnauthorized: () => ref.read(authTokenProvider.notifier).clear(),
  );
  ref.onDispose(client.close);
  return client;
});
