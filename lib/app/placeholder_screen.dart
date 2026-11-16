import 'package:flutter/material.dart';

/// Stand-in body for a destination whose feature screen is not built yet.
/// Feature tasks replace the builder in `feature_routes.dart`.
class PlaceholderScreen extends StatelessWidget {
  const PlaceholderScreen(this.title, {super.key, this.actions = const []});

  final String title;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Semantics(
              header: true,
              child: Text(title,
                  style: Theme.of(context).textTheme.headlineSmall,
                  textAlign: TextAlign.center),
            ),
            for (final a in actions) ...[const SizedBox(height: 12), a],
          ],
        ),
      ),
    );
  }
}
