import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'dart:convert';
import 'package:mime/mime.dart';

/// Service for submitting anonymous reports to the backend API.
///
/// PRIVACY: This service deliberately avoids any device fingerprinting.
/// No device ID, no app ID headers are sent.
class ReportService extends ChangeNotifier {
  // Configure API URL from environment or default
  static const String _baseUrl =
      String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000/api/v1');

  bool _isLoading = false;
  String? _lastError;
  String? _lastReportId;

  bool get isLoading => _isLoading;
  String? get lastError => _lastError;
  String? get lastReportId => _lastReportId;

  /// Submit an anonymous report.
  ///
  /// Returns the report ID on success.
  /// Throws on failure.
  Future<String> submitReport({
    String? textContent,
    String? userCategory,
    String? locationHint,
    String? audioPath,
    String? imagePath,
  }) async {
    _isLoading = true;
    _lastError = null;
    notifyListeners();

    try {
      final uri = Uri.parse('$_baseUrl/reports/submit');
      final request = http.MultipartRequest('POST', uri);

      // PRIVACY: Do NOT add any identifying headers
      // No 'X-Device-ID', no 'X-App-Version', no custom tracking headers
      request.headers['Content-Type'] = 'multipart/form-data';

      // Add form fields
      if (textContent != null && textContent.isNotEmpty) {
        request.fields['text_content'] = textContent;
      }
      if (userCategory != null) {
        request.fields['user_category'] = userCategory;
      }
      if (locationHint != null && locationHint.isNotEmpty) {
        request.fields['location_hint'] = locationHint;
      }

      // Add audio file
      if (audioPath != null) {
        final audioFile = File(audioPath);
        if (await audioFile.exists()) {
          request.files.add(
            await http.MultipartFile.fromPath(
              'audio_file',
              audioPath,
              contentType: MediaType('audio', 'wav'),
              // PRIVACY: Use generic filename — not original device filename
              filename: 'audio.wav',
            ),
          );
        }
      }

      // Add image file
      if (imagePath != null) {
        final imageFile = File(imagePath);
        if (await imageFile.exists()) {
          final mimeType = lookupMimeType(imagePath) ?? 'image/jpeg';
          final parts = mimeType.split('/');
          request.files.add(
            await http.MultipartFile.fromPath(
              'image_file',
              imagePath,
              contentType: MediaType(parts[0], parts[1]),
              // PRIVACY: Use generic filename
              filename: 'image.${parts[1]}',
            ),
          );
        }
      }

      // Send request
      final streamedResponse = await request.send().timeout(
        const Duration(seconds: 30),
        onTimeout: () => throw Exception('Connection timed out. Please try again.'),
      );

      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 202) {
        final data = jsonDecode(response.body);
        final reportId = data['report_id'] as String;
        _lastReportId = reportId;
        return reportId;
      } else if (response.statusCode == 429) {
        throw Exception('Service temporarily at capacity. Please try again in a few minutes.');
      } else if (response.statusCode >= 500) {
        throw Exception('Server error. Please try again later.');
      } else {
        final data = jsonDecode(response.body);
        throw Exception(data['detail'] ?? 'Submission failed');
      }
    } on SocketException {
      throw Exception('No internet connection. Please check your network and try again.');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
