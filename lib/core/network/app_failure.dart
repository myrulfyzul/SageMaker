/// Every outcome of an API call that is not a success.
sealed class AppFailure implements Exception {
  const AppFailure(this.message);

  final String message;

  @override
  String toString() => '$runtimeType: $message';
}

/// Socket, DNS or CORS error. [baseUrl] is shown in the unreachable message.
class NetworkFailure extends AppFailure {
  const NetworkFailure({this.baseUrl, String message = 'Network unavailable'})
      : super(message);

  final String? baseUrl;
}

/// No response within the allowed time (10 s reachability, 15 s requests).
class TimeoutFailure extends AppFailure {
  const TimeoutFailure({this.baseUrl, String message = 'Request timed out'})
      : super(message);

  final String? baseUrl;
}

/// HTTP 5xx.
class ServerFailure extends AppFailure {
  const ServerFailure({
    this.statusCode = 500,
    this.code,
    String message = 'Server error',
  }) : super(message);

  final int statusCode;
  final String? code;
}

/// HTTP 401.
class UnauthorizedFailure extends AppFailure {
  const UnauthorizedFailure(
      {this.code, String message = 'Please sign in again'})
      : super(message);

  final String? code;
}

/// HTTP 403.
class ForbiddenFailure extends AppFailure {
  const ForbiddenFailure({String message = 'Not allowed'}) : super(message);
}

/// HTTP 422 (or 400) with per-field reasons.
class ValidationFailure extends AppFailure {
  const ValidationFailure({
    this.fields = const {},
    String message = 'Please check the highlighted fields',
  }) : super(message);

  /// Field name to reason.
  final Map<String, String> fields;
}

/// HTTP 409.
class ConflictFailure extends AppFailure {
  const ConflictFailure({
    required this.code,
    this.details = const [],
    String message = 'Conflict',
  }) : super(message);

  final String code;
  final List<dynamic> details;
}

/// HTTP 429, for example the login lockout (Req 5.3).
class RateLimitedFailure extends AppFailure {
  const RateLimitedFailure({
    this.retryAfterSeconds,
    String message = 'Too many attempts',
  }) : super(message);

  /// Remaining wait in seconds, when the server reported it.
  final int? retryAfterSeconds;
}

/// HTTP 404.
class NotFoundFailure extends AppFailure {
  const NotFoundFailure({String message = 'Not found'}) : super(message);
}
