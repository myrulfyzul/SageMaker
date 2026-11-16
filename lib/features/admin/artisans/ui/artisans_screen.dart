import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../data/artisan_models.dart';
import '../state/artisans_provider.dart';
import 'artisan_form_screen.dart';

/// Staff artisan list with availability, and an entry to create or edit
/// (Req 23.1, 23.3).
class ArtisansScreen extends ConsumerWidget {
  const ArtisansScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final artisans = ref.watch(artisansProvider);
    Future<void> open(int? id) async {
      await Navigator.of(context).push(MaterialPageRoute<void>(
          builder: (_) => ArtisanFormScreen(artisanId: id)));
      ref.invalidate(artisansProvider);
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Artisans')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => open(null),
        icon: const Icon(Icons.add),
        label: const Text('Add artisan'),
      ),
      body: AsyncValueView<List<Artisan>>(
        value: artisans,
        onRetry: () => ref.invalidate(artisansProvider),
        isEmpty: (items) => items.isEmpty,
        emptyMessage: 'No artisans yet.',
        emptyActionLabel: 'Add artisan',
        onEmptyAction: () => open(null),
        errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
        data: (items) => RefreshIndicator(
          onRefresh: () async => ref.invalidate(artisansProvider),
          child: ListView(
            padding: const EdgeInsets.only(bottom: 88),
            children: [
              for (final a in items)
                ListTile(
                  key: ValueKey('artisan-${a.id}'),
                  title: Text(a.name),
                  subtitle: Text(a.specialisation),
                  trailing: Chip(
                    avatar: a.availability == 'unavailable'
                        ? Icon(Icons.block,
                            size: 16,
                            color: Theme.of(context).colorScheme.error)
                        : null,
                    label: Text(availabilityLabel(a.availability)),
                  ),
                  onTap: () => open(a.id),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

String availabilityLabel(String a) => switch (a) {
      'available' => 'Available',
      'busy' => 'Busy',
      'unavailable' => 'Unavailable',
      _ => a,
    };
