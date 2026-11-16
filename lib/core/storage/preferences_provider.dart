import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Async init of SharedPreferences. Resolves to null when storage is blocked,
/// so callers continue in memory.
final sharedPreferencesProvider =
    FutureProvider<SharedPreferences?>((ref) async {
  try {
    return await SharedPreferences.getInstance();
  } catch (_) {
    return null;
  }
});
