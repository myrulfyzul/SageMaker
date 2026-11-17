import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// App bar back button that always works: it goes back when there is a screen
/// to return to, otherwise it opens [fallback] (for example after a payment,
/// when the confirmation replaced the checkout screens).
class FallbackBackButton extends StatelessWidget {
  const FallbackBackButton({super.key, required this.fallback});
  final String fallback;

  @override
  Widget build(BuildContext context) => IconButton(
        key: const Key('fallback-back'),
        tooltip: 'Back',
        icon: const Icon(Icons.arrow_back),
        onPressed: () => goBackOr(context, fallback),
      );
}

/// Pops the current screen, or opens [fallback] when nothing is underneath.
void goBackOr(BuildContext context, String fallback) {
  final router = GoRouter.of(context);
  if (router.canPop()) {
    router.pop();
  } else {
    router.go(fallback);
  }
}

/// Makes the Android back button (and back gesture) open [fallback] instead of
/// closing the app when this screen has nothing underneath it.
class BackFallback extends StatelessWidget {
  const BackFallback({super.key, required this.fallback, required this.child});
  final String fallback;
  final Widget child;

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: GoRouter.of(context).canPop(),
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) GoRouter.of(context).go(fallback);
        },
        child: child,
      );
}
