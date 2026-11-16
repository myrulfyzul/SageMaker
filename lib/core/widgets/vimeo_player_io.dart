import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

/// Android and iOS: the Vimeo player page inside a WebView.
Widget buildVimeoPlayer(String url) => _VimeoWebView(url: url);

class _VimeoWebView extends StatefulWidget {
  const _VimeoWebView({required this.url});
  final String url;

  @override
  State<_VimeoWebView> createState() => _VimeoWebViewState();
}

class _VimeoWebViewState extends State<_VimeoWebView> {
  late final WebViewController _controller = WebViewController()
    ..setJavaScriptMode(JavaScriptMode.unrestricted)
    ..setBackgroundColor(Colors.black)
    ..loadRequest(Uri.parse(widget.url));

  @override
  Widget build(BuildContext context) => WebViewWidget(controller: _controller);
}
