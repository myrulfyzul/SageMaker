import 'package:glados/glados.dart';
import 'package:sagemaker_flutter/core/constants.dart';
import 'package:sagemaker_flutter/core/validators.dart';

// Feature: sagemaker-asia-mobile-platform, Property 17: Delivery and field validators
// **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 12.3, 12.4, 16.1, 16.8**

String rep(String c, int n) => List.filled(n, c).join();

void main() {
  group('Property 17: delivery and field validators', () {
    Glados(any.intInRange(0, 130))
        .test('name accepted iff 2..100 chars after trim', (n) {
      final v = rep('a', n);
      expect(validateName(v) == null, n >= 2 && n <= 100);
      expect(validateName('  ${rep('a', n)}  ') == null, n >= 2 && n <= 100);
    });

    Glados(any.intInRange(0, 300)).test('address accepted iff 10..255 chars',
        (n) {
      expect(validateAddress(rep('b', n)) == null, n >= 10 && n <= 255);
    });

    Glados(any.intInRange(0, 600)).test('notes accepted iff at most 500 chars',
        (n) {
      expect(validateNotes(rep('n', n)) == null, n <= 500);
    });

    Glados(any.intInRange(0, 300)).test('email length limit of 254', (n) {
      // local part padded so total length is n (min valid form is "a@b.c" = 5)
      final domain = '@b.co';
      final local = n > domain.length ? rep('a', n - domain.length) : '';
      final v = '$local$domain';
      final expected = local.isNotEmpty && v.length <= 254;
      expect(validateEmail(v) == null, expected);
    });

    Glados(any.letterOrDigits).test('email without @ is rejected', (s) {
      expect(validateEmail(s), isNotNull);
    });

    Glados(any.intInRange(0, 9)).test('postcode accepted iff exactly 5 digits',
        (n) {
      expect(validatePostcode(rep('7', n)) == null, n == 5);
      expect(validatePostcode('${rep('7', 4)}x'), isNotNull);
    });

    Glados(any.letterOrDigits).test('postcode matches 5-digit rule', (s) {
      expect(validatePostcode(s) == null,
          RegExp(r'^[0-9]{5}$').hasMatch(s.trim()));
    });

    Glados(any.intInRange(0, 20)).test('state accepted iff in the 16 states',
        (i) {
      expect(malaysianStates.length, 16);
      if (i < 16) {
        expect(validateState(malaysianStates.elementAt(i)), isNull);
      } else {
        expect(validateState('Atlantis$i'), isNotNull);
      }
    });

    Glados(any.letterOrDigits).test('arbitrary text is a state only if listed',
        (s) {
      expect(validateState(s) == null, malaysianStates.contains(s.trim()));
    });

    Glados(any.intInRange(0, 10))
        .test('Malaysian phone: valid prefixes and lengths', (k) {
      // mobile: 01x + 7-8 more digits
      expect(validateMalaysianPhone('01${rep('2', 8)}'), isNull);
      expect(validateMalaysianPhone('+601${rep('2', 8)}'), isNull);
      expect(validateMalaysianPhone('01 2-345 6789'), isNull);
      expect(validateMalaysianPhone('03${rep('4', 8)}'), isNull);
      // too short / non-digit / wrong prefix
      expect(validateMalaysianPhone(rep('1', k)), isNotNull);
      expect(validateMalaysianPhone('02${rep('4', 8)}'), isNotNull);
      expect(validateMalaysianPhone('01234abc89'), isNotNull);
      expect(validateMalaysianPhone(''), isNotNull);
    });

    Glados(any.intInRange(0, 25))
        .test('profile phone accepted iff 8..15 digits', (n) {
      expect(validateProfilePhone(rep('5', n)) == null, n >= 8 && n <= 15);
      expect(validateProfilePhone('${rep('5', 8)}x'), isNotNull);
    });

    Glados(any.intInRange(0, 140))
        .test('password accepted iff 8..128 with letter and digit', (n) {
      final withBoth = n >= 2 ? 'a1${rep('x', n - 2)}' : rep('a', n);
      expect(validatePassword(withBoth) == null, n >= 8 && n <= 128);
      if (n >= 8 && n <= 128) {
        expect(validatePassword(rep('a', n)), isNotNull);
        expect(validatePassword(rep('1', n)), isNotNull);
      }
    });

    Glados(any.letterOrDigits).test('url requires http(s) scheme and host',
        (s) {
      expect(
          validateUrl('https://$s.example.com/p') == null || s.isEmpty, isTrue);
      expect(validateUrl('ftp://$s.example.com'), isNotNull);
      expect(validateUrl(s), isNotNull);
    });
  });
}
