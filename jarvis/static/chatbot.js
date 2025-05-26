$(document).ready(function () {
    $('#chatbot-toggle-btn').on('click', toggleChatbot);
    $('#close-btn').on('click', toggleChatbot);
    $('#query').on('keypress', function (event) {
        if (event.key === 'Enter') sendQuery();
    });
    $('#send-btn').on('click', sendQuery);

    showInitialMessage();
});

function showInitialMessage() {
    $('#chat').append('<li class="chat bot-message"><p>Olá! Como posso ajudar?</p></li>');

    const suggestions = [
        "O Município de Viana do Castelo com uma extensão de linha de costa de?",
        "O que Compete ao CMAACVC?",
        "Que estudantes podem candidatar -se à atribuição de bolsas de estudo?"
    ];

    let suggestionsHtml = '<div class="suggestions">';
    suggestions.forEach(question => {
        suggestionsHtml += `<div class="suggestion" onclick="sendSuggestedQuery('${question}')">${question}</div>`;
    });
    suggestionsHtml += '</div>';

    $('#chat').append(suggestionsHtml);
}

function sendSuggestedQuery(question) {
    $('#query').val(question);
    sendQuery();
}

function sendQuery() {
    const queryText = $('#query').val().trim();
    if (!queryText) return;

    $('#query').val('');
    $('#chat').append('<li class="chat user-message"><p>' + queryText + '</p></li>');

    $('.suggestions').remove();

    $.ajax({
        url: '/query',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ query_text: queryText }),
        success: function (response) {
            $('#chat').append('<li class="chat bot-message"><p>' + response.response + '</p></li>');
            $('#chat').scrollTop($('#chat')[0].scrollHeight);
        },
        error: function () {
            $('#chat').append('<li class="chat bot-message"><p>Desculpe, algo deu errado. Tente novamente mais tarde! </p></li>');
            $('#chat').scrollTop($('#chat')[0].scrollHeight);
        }
    });
}

function toggleChatbot() {
    $('#chatbot-popup').toggle();
    $('#chatbot-toggle-btn').toggle();
}


