import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/material.dart';

import 'empty_view.dart';
import 'error_view.dart';
import 'loading_view.dart';

/// Renders loading, error (with retry) and empty states for an [AsyncValue]
/// (Req 3.3 to 3.6). A failed refresh keeps previous data visible.
class AsyncValueView<T> extends StatelessWidget {
  const AsyncValueView({
    super.key,
    required this.value,
    required this.data,
    required this.onRetry,
    this.isEmpty,
    this.emptyMessage = 'Nothing here yet.',
    this.emptyActionLabel = 'Browse products',
    required this.onEmptyAction,
    this.errorMessage = defaultErrorMessage,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final VoidCallback onRetry;

  /// Returns true when [data] should render the empty state.
  final bool Function(T data)? isEmpty;
  final String emptyMessage;
  final String emptyActionLabel;
  final VoidCallback onEmptyAction;
  final String Function(Object error) errorMessage;

  /// Maps an error to a reason: network unavailable, timeout or server error.
  static String defaultErrorMessage(Object error) {
    final name = error.runtimeType.toString().toLowerCase();
    if (name.contains('timeout')) return 'Request timed out';
    if (name.contains('network') || name.contains('socket')) {
      return 'Network unavailable';
    }
    return 'Server error';
  }

  @override
  Widget build(BuildContext context) {
    if (value.hasValue) {
      final v = value.requireValue;
      final empty = isEmpty?.call(v) ?? false;
      if (empty) {
        return EmptyView(
          message: emptyMessage,
          actionLabel: emptyActionLabel,
          onAction: onEmptyAction,
        );
      }
      final child = data(v);
      if (value.hasError) {
        return Column(
          children: [
            MaterialBanner(
              content: Text(errorMessage(value.error!)),
              actions: [
                TextButton(onPressed: onRetry, child: const Text('Retry')),
              ],
            ),
            Expanded(child: child),
          ],
        );
      }
      return child;
    }
    if (value.hasError) {
      return ErrorView(message: errorMessage(value.error!), onRetry: onRetry);
    }
    return const LoadingView();
  }
}
