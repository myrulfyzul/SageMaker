import 'package:flutter_test/flutter_test.dart';
import 'package:glados/glados.dart' hide expect, group, test, setUp, tearDown;
import 'package:sagemaker_flutter/core/badge.dart';
import 'package:sagemaker_flutter/core/constants.dart';
import 'package:sagemaker_flutter/core/money.dart';
import 'package:sagemaker_flutter/core/validators.dart';

void main() {
  group('formatRm', () {
    test('matches the legacy money() output', () {
      expect(formatRm(0), 'RM 0.00');
      expect(formatRm(5), 'RM 0.05');
      expect(formatRm(1250), 'RM 12.50');
      expect(formatRm(99999999), 'RM 999999.99');
    });
  });

  group('badgeLabel', () {
    test('hidden, decimal and 99+', () {
      expect(badgeLabel(0), isNull);
      expect(badgeLabel(-3), isNull);
      expect(badgeLabel(1), '1');
      expect(badgeLabel(99), '99');
      expect(badgeLabel(100), '99+');
      expect(badgeLabel(5000), '99+');
    });
  });

  group('validators', () {
    test('name', () {
      expect(validateName('A'), isNotNull);
      expect(validateName(' A '), isNotNull);
      expect(validateName('Ai'), isNull);
      expect(validateName('x' * 101), isNotNull);
    });
    test('email', () {
      expect(validateEmail('a@b.com'), isNull);
      expect(validateEmail('a@b'), isNotNull);
      expect(validateEmail('a b@c.com'), isNotNull);
    });
    test('malaysian phone', () {
      expect(validateMalaysianPhone('012-345 6789'), isNull);
      expect(validateMalaysianPhone('+60123456789'), isNull);
      expect(validateMalaysianPhone('0312345678'), isNull);
      expect(validateMalaysianPhone('0212345678'), isNotNull);
      expect(validateMalaysianPhone('abc'), isNotNull);
    });
    test('profile phone', () {
      expect(validateProfilePhone('12345678'), isNull);
      expect(validateProfilePhone('1234567'), isNotNull);
      expect(validateProfilePhone('+6012345678'), isNotNull);
    });
    test('postcode, address, state, notes', () {
      expect(validatePostcode('50000'), isNull);
      expect(validatePostcode('5000'), isNotNull);
      expect(validateAddress('short'), isNotNull);
      expect(validateAddress('1 Jalan Bunga, Taman'), isNull);
      expect(malaysianStates.length, 16);
      for (final s in malaysianStates) {
        expect(validateState(s), isNull);
      }
      expect(validateState('Texas'), isNotNull);
      expect(validateNotes('n' * 501), isNotNull);
      expect(validateNotes(null), isNull);
    });
    test('password', () {
      expect(validatePassword('abcdefg1'), isNull);
      expect(validatePassword('abcdefgh'), isNotNull);
      expect(validatePassword('12345678'), isNotNull);
      expect(validatePassword('a1'), isNotNull);
      expect(validatePassword('a1' * 65), isNotNull);
    });
    test('url', () {
      expect(validateUrl('https://example.com/a'), isNull);
      expect(validateUrl('ftp://example.com'), isNotNull);
      expect(validateUrl('not a url'), isNotNull);
    });
  });

  group('properties', () {
    Glados(any.intInRange(0, 100000)).test('badgeLabel follows count', (n) {
      final label = badgeLabel(n);
      if (n == 0) {
        expect(label, isNull);
      } else if (n > 99) {
        expect(label, '99+');
      } else {
        expect(label, n.toString());
      }
    });
    Glados(any.intInRange(0, 99999999)).test('formatRm has two decimals', (n) {
      expect(RegExp(r'^RM \d+\.\d{2}$').hasMatch(formatRm(n)), isTrue);
    });
  });
}
