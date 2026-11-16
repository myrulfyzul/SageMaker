/// Client-side mirror of the artisan rules (Req 23.1, 23.2).
String? validateArtisanName(String? v) {
  final t = v?.trim() ?? '';
  if (t.isEmpty || t.length > 100) return 'Name must be 1 to 100 characters';
  return null;
}

String? validateSpecialisation(String? v) {
  final t = v?.trim() ?? '';
  if (t.isEmpty || t.length > 100) {
    return 'Specialisation must be 1 to 100 characters';
  }
  return null;
}

String? validateAvailability(String? v) =>
    const ['available', 'busy', 'unavailable'].contains(v)
        ? null
        : 'Choose available, busy or unavailable';

String? validateStory(String? v) =>
    (v ?? '').length > 2000 ? 'Story must be at most 2000 characters' : null;

String? validateArtisanPhone(String? v) =>
    (v ?? '').trim().length > 30 ? 'Phone must be at most 30 characters' : null;

final RegExp _email = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

String? validateArtisanEmail(String? v) {
  final t = v?.trim() ?? '';
  if (t.isEmpty) return null;
  if (t.length > 254 || !_email.hasMatch(t)) return 'Enter a valid email address';
  return null;
}

String? validateArtisanAddress(String? v) => (v ?? '').trim().length > 300
    ? 'Address must be at most 300 characters'
    : null;
