import torch
from torch import nn
import torch.nn.functional as F


class DotAttention(nn.Module):
    """
    Dot attention calculation
    """
    def __init__(self):
        super(DotAttention, self).__init__()

    def forward(self, enc_states, h_prev):
        """
        calculate the context vector c_t, both the input and output are batch first
        :param enc_states: the encoder states, in shape [batch, seq_len, dim]
        :param h_prev: the previous states of decoder, h_{t-1}, in shape [1, batch, dim]
        :return: c_t: context vector
        """
        alpha_t = torch.bmm(h_prev.transpose(0, 1), enc_states.transpose(1, 2))  # [batch, 1, seq_len]
        alpha_t = F.softmax(alpha_t, dim=-1)
        c_t = torch.bmm(alpha_t, enc_states)  # [batch, 1, dim]
        return c_t


class Model(nn.Module):
    def __init__(self, vocab, out_len=10, emb_dim=32, hid_dim=128):
        super(Model, self).__init__()
        self.out_len = out_len
        self.hid_dim = hid_dim
        self.emb_dim = emb_dim
        self.vocab = vocab

        self.embedding_look_up = nn.Embedding(len(self.vocab), self.emb_dim)

        self.encoder = nn.GRU(self.emb_dim, self.hid_dim//2, batch_first=True, bidirectional=True)
        self.attention_layer = DotAttention()
        self.decoder = nn.GRU(self.emb_dim + self.hid_dim, self.hid_dim, batch_first=True)

        self.decoder2vocab = nn.Linear(self.hid_dim, len(self.vocab))

        self.loss_layer = nn.CrossEntropyLoss()

    def init_hidden(self, batch_size):
        return torch.zeros(2, batch_size, self.hid_dim//2).cuda()

    def forward(self, inputs, targets, test=False):
        embeds = self.embedding_look_up(inputs)
        hidden = self.init_hidden(len(inputs))
        states, hidden = self.encoder(embeds, hidden)
        # logits = self.decode(hidden, targets, test)
        logits = self.attention_decode(states, hidden, targets, test)
        return logits

    def attention_decode(self, enc_states, hidden, targets, test=False):
        hidden = torch.cat([hidden[0], hidden[1]], dim=-1).view(1, -1, self.hid_dim)
        if test:
            words = torch.zeros(hidden.shape[1], self.out_len, dtype=torch.long)
            word = torch.ones(hidden.shape[1], dtype=torch.long).cuda() * self.vocab["<s>"]
            for i in range(self.out_len):
                embeds = self.embedding_look_up(word).view(-1, 1, self.emb_dim)
                c_t = self.attention_layer(enc_states, hidden)
                outputs, hidden = self.decoder(torch.cat([c_t, embeds], dim=-1), hidden)
                logit = F.tanh(self.decoder2vocab(outputs).squeeze())
                probs = F.softmax(logit, dim=-1)
                word = torch.argmax(probs, dim=-1)
                words[:, i] = word
            return words
        else:
            logits = torch.zeros(hidden.shape[1], targets.shape[1]-1, len(self.vocab)).cuda()
            for i in range(targets.shape[1] - 1):
                word = targets[:, i]
                embeds = self.embedding_look_up(word).view(-1, 1, self.emb_dim)
                c_t = self.attention_layer(enc_states, hidden)
                outputs, hidden = self.decoder(torch.cat([c_t, embeds], dim=-1), hidden)
                logits[:, i, :] = self.decoder2vocab(outputs).squeeze()
        return logits

    def my_loss_layer(self, logits, batch_y):
        logits = torch.argmax(logits, -1)
        logits_emb = torch.sum(self.embedding_look_up(logits), dim=1).view(-1, 1, self.emb_dim)
        y_emb = torch.sum(self.embedding_look_up(batch_y), dim=1).view(-1, self.emb_dim, 1)
        loss = torch.exp(-torch.sum(torch.bmm(logits_emb, y_emb)))
        return loss

