import 'package:flutter/material.dart';

/// Centered progress indicator shown while waiting for the API (Req 3.3).
class LoadingView extends StatelessWidget {
  const LoadingView({super.key});

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(semanticsLabel: 'Loading'),
    );
  }
}
