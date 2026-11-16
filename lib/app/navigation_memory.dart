import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// Remembers the last screen the user was allowed to see, so cancelling the
/// login screen returns there and not to the restricted destination
/// (Req 18.8).
class NavigationMemory {
  String lastAllowed = '/';
}

final navigationMemoryProvider = Provider<NavigationMemory>((ref) => NavigationMemory());

/// Leaves the login screen without signing in.
void cancelLogin(GoRouter router, NavigationMemory memory) {
  router.go(memory.lastAllowed);
}
