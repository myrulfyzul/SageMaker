import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/catalogue/data/catalogue_models.dart';
import 'package:sagemaker_flutter/features/catalogue/data/catalogue_repository.dart';
import 'package:sagemaker_flutter/features/catalogue/state/shop_provider.dart';
import 'package:sagemaker_flutter/features/catalogue/ui/product_detail_screen.dart';
import 'package:sagemaker_flutter/features/home/ui/home_screen.dart';

CatalogueProduct product(String id,
        {StockLevel level = StockLevel.inStock,
        int qty = 10,
        bool demo = true,
        String? artisan}) =>
    CatalogueProduct(
      id: id,
      name: 'Bag $id',
      description: 'Handmade',
      category: const CategoryRef(id: 1, slug: 'tote-bags', name: 'Tote bags'),
      priceSen: 4500,
      isDemo: demo,
      imageUrls: const [],
      variations: const [
        ProductVariation(
            id: 1,
            label: 'Large',
            priceSen: 5000,
            isActive: true,
            stockQuantity: 3)
      ],
      stockLevel: level,
      stockQuantity: qty,
      artisanName: artisan,
    );

class FakeRepo extends CatalogueRepository {
  FakeRepo({this.failBest = false}) : super(ApiClient(baseUrl: 'http://x'));
  bool failBest;
  @override
  Future<List<CatalogueProduct>> bestSellers() async {
    if (failBest) throw Exception('boom');
    return [product('1')];
  }

  @override
  Future<List<CatalogueProduct>> newArrivals() async => [product('2')];
  @override
  Future<List<CatalogueProduct>> recommendations() async => [];
  @override
  Future<List<CategoryRef>> categories() async => [];
}

Widget host(Widget child, FakeRepo repo, {List<Override> extra = const []}) =>
    ProviderScope(
      overrides: [
        catalogueRepositoryProvider.overrideWithValue(repo),
        ...extra
      ],
      child: MaterialApp(theme: buildAppTheme(), home: child),
    );

void main() {
  test('stock status text follows Req 9.11', () {
    expect(stockStatusText(StockLevel.inStock, 50), 'In stock');
    expect(stockStatusText(StockLevel.lowStock, 3), 'Low stock: 3 left');
    expect(stockStatusText(StockLevel.outOfStock, 0), 'Out of stock');
  });

  test('validHomeSearch rejects blank and over-long text', () {
    expect(validHomeSearch('   '), isNull);
    expect(validHomeSearch(''), isNull);
    expect(validHomeSearch(' tote '), 'tote');
    expect(validHomeSearch('a' * 101), isNull);
  });

  test('CatalogueProduct.fromJson maps stock, artisan and images', () {
    final p = CatalogueProduct.fromJson({
      'id': 'p1',
      'name': 'N',
      'description': 'D',
      'category': {'id': 2, 'slug': 'toys', 'name': 'Toys'},
      'priceSen': 1200,
      'isDemo': true,
      'images': [
        {'id': 1, 'url': '/media/a.png', 'isDemo': true}
      ],
      'variations': [],
      'stock': {'status': 'low_stock', 'quantity': 2, 'label': 'x'},
      'artisan': {'id': 1, 'name': 'Aminah'},
    });
    expect(p.stockText, 'Low stock: 2 left');
    expect(p.artisanName, 'Aminah');
    expect(p.imageUrls, ['/media/a.png']);
  });

  testWidgets('Home search with whitespace stays and keeps focus',
      (tester) async {
    String? searched;
    await tester.pumpWidget(
        host(HomeScreen(onSearch: (_, q) => searched = q), FakeRepo()));
    await tester.pumpAndSettle();
    final field = find.byKey(const Key('home-search'));
    await tester.tap(field);
    await tester.enterText(field, '   ');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump();
    expect(searched, isNull);
    final editable = tester.widget<EditableText>(
        find.descendant(of: field, matching: find.byType(EditableText)));
    expect(editable.focusNode.hasFocus, isTrue);

    await tester.enterText(field, ' tote ');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pump();
    expect(searched, 'tote');
  });

  testWidgets('a failed Home section shows retry while others stay',
      (tester) async {
    tester.view.physicalSize = const Size(800, 3000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final repo = FakeRepo(failBest: true);
    await tester.pumpWidget(host(const HomeScreen(), repo));
    await tester.pumpAndSettle();
    expect(find.text('Retry'), findsNWidgets(2));
    expect(find.text('Bag 2'), findsOneWidget);
    repo.failBest = false;
    await tester.tap(find.text('Retry').first);
    await tester.pumpAndSettle();
    expect(find.text('Bag 1'), findsOneWidget);
  });

  testWidgets('out of stock disables add to cart and shows status',
      (tester) async {
    await tester.pumpWidget(host(
        Scaffold(
            body: ProductDetailBody(
                product: product('9',
                    level: StockLevel.outOfStock, qty: 0, artisan: 'Aminah'))),
        FakeRepo()));
    expect(find.text('Out of stock'), findsWidgets);
    expect(find.text('Made by Aminah'), findsOneWidget);
    expect(find.text('Demo'), findsWidgets);
    final btn =
        tester.widget<FilledButton>(find.byKey(const Key('add-to-cart')));
    expect(btn.onPressed, isNull);
  });

  testWidgets('in-stock product adds to cart via the hook', (tester) async {
    int? variation;
    await tester.pumpWidget(host(
        Scaffold(body: ProductDetailBody(product: product('3'))), FakeRepo(),
        extra: [
          addToCartProvider.overrideWithValue((p, v) async {
            variation = v;
            return null;
          })
        ]));
    await tester.tap(find.textContaining('Large'));
    await tester.pump();
    await tester.tap(find.byKey(const Key('add-to-cart')));
    await tester.pump();
    expect(variation, 1);
    expect(find.text('Bag 3 added to cart'), findsOneWidget);
  });
}


