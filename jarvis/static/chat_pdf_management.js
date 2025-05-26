$(document).ready(function () {
    function loadPDFs() {
        $.ajax({
            url: '/get_pdfs',
            method: 'GET',
            success: function (response) {
                if (response.length === 0) {
                    $('#pdf-list').html('<p>No PDFs uploaded.</p>');
                } else {
                    let pdfHtml = '';
                    response.forEach(function (pdf) {
                        pdfHtml += `
                            <div>
                                <a href="/download_pdf/${pdf.id}" target="_blank">${pdf.file_name}</a>
                                <button class="delete-pdf" data-id="${pdf.id}">Delete</button>
                            </div>
                        `;
                    });
                    $('#pdf-list').html(pdfHtml);
                }
            },
            error: function () {
                $('#pdf-list').html('<p>Error fetching PDF list.</p>');
            }
        });
    }

    loadPDFs();

    // Handle PDF upload
    $('#upload-form').on('submit', function (event) {
        event.preventDefault();
        var formData = new FormData();
        formData.append('file', $('#pdf-file')[0].files[0]);

        $.ajax({
            url: '/upload',
            method: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (response) {
                alert(response.message);
                loadPDFs();
            },
            error: function (xhr) {
                alert('Error uploading file: ' + xhr.responseJSON.error);
            }
        });
    });

    // Handle PDF deletion
    $(document).on('click', '.delete-pdf', function () {
        var pdfId = $(this).data('id');

        if (!pdfId) {
            alert('Invalid ID');
            return;
        }

        $.ajax({
            url: '/delete',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ id: pdfId }),
            success: function (response) {
                alert(response.message);
                loadPDFs();
            },
            error: function (xhr) {
                alert('Error deleting file: ' + xhr.responseJSON.error);
            }
        });
    });

    // Display selected file name
    $('#pdf-file').on('change', function () {
        var fileName = $(this).val().split('\\').pop();
        $('#file-name').text('Selected file: ' + fileName);
    });

    // Fetch chat history
    $.ajax({
        url: '/get_chat_history',
        method: 'GET',
        success: function (response) {
            if (response.length === 0) {
                $('#chat-history').html('<p>No chat history available.</p>');
            } else {
                let chatHtml = '';
                response.forEach(function (entry) {
                    chatHtml += `
                        <div class="chat-entry">
                            <p class="user-message">User: ${entry.user_message}</p>
                            <p class="bot-response">Bot: ${entry.bot_response}</p>
                            <p><small>Time: ${entry.chat_timestamp}</small></p>
                        </div>
                    `;
                });
                $('#chat-history').html(chatHtml);
            }
        },
        error: function () {
            $('#chat-history').html('<p>Error fetching chat history.</p>');
        }
    });

    // Handle chat history search
    $('#search-btn').on('click', function () {
        const date = $('#search-date').val();
        const keywords = $('#search-keywords').val();

        $.ajax({
            url: '/search_chat_history',
            method: 'GET',
            data: { date: date, keywords: keywords },
            success: function (response) {
                let chatHtml = '';
                if (response.length === 0) {
                    chatHtml = '<p>No chat history found.</p>';
                } else {
                    response.forEach(function (entry) {
                        chatHtml += `
                            <div class="chat-entry">
                                <p class="user-message">User: ${entry.user_message}</p>
                                <p class="bot-response">Bot: ${entry.bot_response}</p>
                                <p><small>Time: ${entry.chat_timestamp}</small></p>
                            </div>
                        `;
                    });
                }
                $('#chat-history').html(chatHtml);
            },
            error: function () {
                $('#chat-history').html('<p>Error fetching chat history.</p>');
            }
        });
    });

    $(document).ready(function() {
            // Click event for the "Run Script" button
            $('#run-script-btn').click(function() {
                // Show loading message
                $('#script-status').text('Running script... Please wait.');

                // Call the backend route to execute the Python script
                $.get('/run_script', function(response) {
                    $('#script-status').text(response.message);
                }).fail(function(error) {
                    $('#script-status').text('Error: ' + error.responseJSON.message);
                });
            });
    });
});
