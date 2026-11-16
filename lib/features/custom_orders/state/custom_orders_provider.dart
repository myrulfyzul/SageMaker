import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/network/api_client.dart';
import '../data/custom_order_models.dart';
import '../data/custom_orders_repository.dart';

final customOrdersRepositoryProvider = Provider<CustomOrdersRepository>(
    (ref) => CustomOrdersRepository(ref.watch(apiClientProvider)));

/// All of the customer's custom orders, newest first (Req 16.5). Reloaded
/// each time the screen opens so staff estimates and statuses show (16.6).
final customOrdersProvider =
    FutureProvider.autoDispose<List<CustomOrder>>((ref) async {
  final repo = ref.watch(customOrdersRepositoryProvider);
  final all = <CustomOrder>[];
  while (true) {
    final page = await repo.list(offset: all.length);
    all.addAll(page.items);
    if (!page.hasMore || page.items.isEmpty) return all;
  }
});

final customOrderDetailProvider = FutureProvider.autoDispose
    .family<CustomOrder, int>(
        (ref, id) => ref.watch(customOrdersRepositoryProvider).get(id));

/// Opens the gallery for multiple images. Overridable in tests.
typedef ImagePickerFn = Future<List<PickedImage>> Function(int limit);

final imagePickerProvider = Provider<ImagePickerFn>((ref) => (limit) async {
      final picker = ImagePicker();
      // pickMultiImage requires a limit of at least 2.
      final files = limit < 2
          ? [
              if (await picker.pickImage(source: ImageSource.gallery)
                  case final one?)
                one
            ]
          : await picker.pickMultiImage(limit: limit);
      return [
        for (final f in files) PickedImage(f.name, await f.readAsBytes())
      ];
    });
