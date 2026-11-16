import 'package:flutter/foundation.dart';
import 'package:glados/glados.dart';
import 'package:sagemaker_flutter/core/config/api_config.dart';

// Feature: sagemaker-asia-mobile-platform, Property 5: API base URL validation
// and precedence.
// **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**

const _hostChars = 'abcdefghijklmnopqrstuvwxyz0123456789';

String _host(List<int> seeds) {
  final n = seeds.isEmpty ? 1 : seeds.length;
  final b = StringBuffer();
  for (var i = 0; i < n; i++) {
    final s = seeds.isEmpty ? 0 : seeds[i];
    b.write(_hostChars[s.abs() % _hostChars.length]);
  }
  return b.toString();
}

void main() {
  Glados2(any.list(any.positiveIntOrZero), any.bool).test(
    'http/https URL with host and length <= 2048 is accepted',
    (seeds, https) {
      final url = '${https ? 'https' : 'http'}://${_host(seeds)}.example';
      expect(isValidApiBaseUrl(url), isTrue, reason: url);
    },
  );

  Glados2(any.list(any.positiveIntOrZero),
      any.choose(['ftp', 'ws', 'file', 'mailto', 'javascript'])).test(
    'non-http(s) schemes are rejected',
    (seeds, scheme) {
      expect(isValidApiBaseUrl('$scheme://${_host(seeds)}.example'), isFalse);
    },
  );

  Glados(any.list(any.positiveIntOrZero)).test(
    'relative, hostless and over-long values are rejected',
    (seeds) {
      final h = _host(seeds);
      expect(isValidApiBaseUrl('$h.example/path'), isFalse);
      expect(isValidApiBaseUrl('/$h'), isFalse);
      expect(isValidApiBaseUrl('http://'), isFalse);
      expect(isValidApiBaseUrl('https:///$h'), isFalse);
      final prefix = 'http://$h.example/';
      final okLen = prefix + 'a' * (maxApiBaseUrlLength - prefix.length);
      expect(okLen.length, maxApiBaseUrlLength);
      expect(isValidApiBaseUrl(okLen), isTrue);
      expect(isValidApiBaseUrl('${okLen}a'), isFalse);
    },
  );

  test('null and empty are rejected', () {
    expect(isValidApiBaseUrl(null), isFalse);
    expect(isValidApiBaseUrl(''), isFalse);
  });

  Glados2(any.choose(['', 'http://', 'https://', 'ftp://', '/', 'HTTP://']),
          any.letterOrDigits)
      .test(
    'any accepted string is an http(s) URL within the length limit',
    (pre, rest) {
      final s = '$pre$rest.x:80/p';
      if (isValidApiBaseUrl(s)) {
        expect(s.length, lessThanOrEqualTo(maxApiBaseUrlLength));
        expect(
          s.startsWith('http://') ||
              s.startsWith('https://') ||
              s.toLowerCase().startsWith('http'),
          isTrue,
        );
        expect(Uri.parse(s).host, isNotEmpty);
      }
    },
  );

  Glados3(any.list(any.positiveIntOrZero), any.list(any.positiveIntOrZero),
          any.list(any.positiveIntOrZero))
      .test('precedence: override, then non-empty define, then default',
          (a, b, c) {
    final override = 'http://${_host(a)}.o';
    final define = 'https://${_host(b)}.d';
    final def = 'http://${_host(c)}.p';
    expect(
      resolveApiBaseUrl(
          override: override, define: define, platformDefault: def),
      override,
    );
    expect(
      resolveApiBaseUrl(override: null, define: define, platformDefault: def),
      define,
    );
    expect(
      resolveApiBaseUrl(override: '', define: define, platformDefault: def),
      define,
    );
    expect(
      resolveApiBaseUrl(override: null, define: '', platformDefault: def),
      def,
    );
    // trailing slashes are stripped
    expect(
      resolveApiBaseUrl(override: '$override///', platformDefault: def),
      override,
    );
  });

  test('platform default: android emulator alias, otherwise localhost', () {
    expect(
      platformDefaultBaseUrl(isWeb: false, platform: TargetPlatform.android),
      'http://10.0.2.2:8000',
    );
    for (final p in [
      TargetPlatform.iOS,
      TargetPlatform.windows,
      TargetPlatform.macOS
    ]) {
      expect(platformDefaultBaseUrl(isWeb: false, platform: p),
          'http://localhost:8000');
    }
    expect(
        platformDefaultBaseUrl(isWeb: true, platform: TargetPlatform.android),
        'http://localhost:8000');
  });
}
