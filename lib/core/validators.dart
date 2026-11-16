import 'constants.dart';

/// Client-side validators mirroring the backend rules
/// (checkout/schemas.py, users/schemas.py, auth/schemas.py).
/// Each returns `null` when valid, otherwise an error message.
final RegExp _postcodeRe = RegExp(r'^[0-9]{5}$');
final RegExp _emailRe = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');
final RegExp _myPhoneRe = RegExp(r'^(?:\+?60|0)(?:1[0-9]{8,9}|[3-9][0-9]{7,8})$');
final RegExp _profilePhoneRe = RegExp(r'^[0-9]{8,15}$');
final RegExp _letterRe = RegExp(r'\p{L}', unicode: true);
final RegExp _digitRe = RegExp(r'[0-9]');

/// Name: 2 to 100 characters after trimming (checkout delivery rule).
String? validateName(String? value) {
  final v = value?.trim() ?? '';
  if (v.length < 2 || v.length > 100) return 'Name must be 2 to 100 characters';
  return null;
}

/// Email: valid format, at most 254 characters.
String? validateEmail(String? value) {
  final v = value?.trim() ?? '';
  if (v.length > 254 || !_emailRe.hasMatch(v)) {
    return 'Enter a valid email address of at most 254 characters';
  }
  return null;
}

/// Malaysian phone (checkout): optional +60 / 60 / 0 prefix; spaces and dashes ignored.
String? validateMalaysianPhone(String? value) {
  final v = (value?.trim() ?? '').replaceAll(RegExp(r'[\s-]'), '');
  if (!_myPhoneRe.hasMatch(v)) return 'Enter a valid Malaysian phone number';
  return null;
}

/// Profile / saved-address phone: 8 to 15 digits (users module).
String? validateProfilePhone(String? value) {
  if (!_profilePhoneRe.hasMatch(value ?? '')) return 'Phone must be 8 to 15 digits';
  return null;
}

/// Postcode: exactly 5 digits.
String? validatePostcode(String? value) {
  if (!_postcodeRe.hasMatch(value?.trim() ?? '')) return 'Postcode must be exactly 5 digits';
  return null;
}

/// Delivery address: 10 to 255 characters after trimming.
String? validateAddress(String? value) {
  final v = value?.trim() ?? '';
  if (v.length < 10 || v.length > 255) return 'Address must be 10 to 255 characters';
  return null;
}

/// State: one of the 16 Malaysian states and federal territories.
String? validateState(String? value) {
  if (value == null || !malaysianStates.contains(value.trim())) {
    return 'Choose one of the 16 Malaysian states';
  }
  return null;
}

/// Delivery notes: optional, at most 500 characters after trimming.
String? validateNotes(String? value) {
  if (value != null && value.trim().length > 500) return 'Notes must be at most 500 characters';
  return null;
}

/// Password: 8 to 128 characters with at least one letter and one digit.
String? validatePassword(String? value) {
  final v = value ?? '';
  if (v.length < 8 || v.length > 128) return 'Password must be 8 to 128 characters';
  if (!_letterRe.hasMatch(v)) return 'Password must contain at least one letter';
  if (!_digitRe.hasMatch(v)) return 'Password must contain at least one digit';
  return null;
}

/// URL: absolute http or https URL with a host.
String? validateUrl(String? value) {
  final uri = Uri.tryParse(value?.trim() ?? '');
  if (uri == null ||
      !(uri.scheme == 'http' || uri.scheme == 'https') ||
      uri.host.isEmpty) {
    return 'Enter a valid http or https URL';
  }
  return null;
}
