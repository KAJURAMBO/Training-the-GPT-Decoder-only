"""
Time Series Transformer
"""
from pprint import pprint
import math
import numpy as np
import tensorflow as tf
import os
keras = tf.keras        # silly imports to work around PyCharm inspections
layers = keras.layers
from keras.callbacks import EarlyStopping, ModelCheckpoint
from keras import backend as K


class Head(layers.Layer):
    def __init__(self, head_size, seq_len, dropout):
        super().__init__()
        self.head_size = head_size
        self.seq_len = seq_len
        self.dropout_rate = dropout

    def build(self, input_shape):
        self.key = layers.Dense(self.head_size, activation=None, use_bias=False)
        self.query = layers.Dense(self.head_size, activation=None, use_bias=False)
        self.value = layers.Dense(self.head_size, activation=None, use_bias=False)
        self.dropout = layers.Dropout(self.dropout_rate)
        self.mask = tf.constant(np.tril(np.ones((self.seq_len, self.seq_len))))

    def call(self, x, *args, **kwargs):
        k = self.key(x)     # (B,T,C)
        q = self.query(x)   # (B,T,C)

        # compute attention scores ("affinities")
        k_transposed = K.permute_dimensions(k, (0, 2, 1))   # B, C, T
        wei = tf.matmul(q, k_transposed)    # B, T, T
        wei /= math.sqrt(C)     # scale
        wei = layers.Softmax(axis=-1)(wei, self.mask)   # softmax while making the upper-triangle all 0
        wei = self.dropout(wei)

        # perform the weighted aggregation of the values
        v = self.value(x)   # B, T, C
        out = tf.matmul(wei, v)      # (B, T, T) @ (B, T, C) -> (B, T, C)

        assert out.shape[-2] == self.seq_len and out.shape[-1] == self.head_size

        return out


def multi_head_self_attention_layer(num_heads, head_size, dropout=0.):

    mha = layers.MultiHeadAttention(
        key_dim=head_size, num_heads=num_heads, output_shape=num_heads * head_size,
        dropout=dropout)

    def _call(x):
        return mha(query=x, value=x, key=x, attention_mask=None)
    
    return _call


class FeedForward(layers.Layer):
    def __init__(self, n_embd: int, dropout: float):
        super().__init__()

        self.n_embd = n_embd
        self.dropout = dropout

    def build(self, input_shape):
        self.net = keras.Sequential([
            layers.LayerNormalization(epsilon=1e-6),
            layers.Conv1D(filters=4, kernel_size=1, activation='relu'),
            layers.Conv1D(filters=self.n_embd, kernel_size=1),
            layers.Dropout(self.dropout)
        ])

    def call(self, x, *args, **kwargs):
        return self.net(x)


class Block(layers.Layer):
    def __init__(self, n_embd: int, n_head: int, dropout: float):
        assert n_embd % n_head == 0
        super().__init__()

        self.n_embd = n_embd
        self.n_head = n_head
        self.head_size = n_embd // n_head
        self.dropout = dropout

    def build(self, input_shape):
        self.sa = multi_head_self_attention_layer(head_size=self.head_size, num_heads=self.n_head)
        self.ffwd = FeedForward(self.n_embd, self.dropout)
        self.ln1 = layers.LayerNormalization(epsilon=1e-5)
        self.ln2 = layers.LayerNormalization(epsilon=1e-5)

    def call(self, x, *args, **kwargs):
        x = x + self.sa(self.ln1(x))
        x = x + self.ffwd(self.ln2(x))
        return x


class TransformerLayer(layers.Layer):
    def __init__(self, vocab_size, n_embd, n_head, n_block, dropout):
        super().__init__()

        self.vocab_size = vocab_size
        self.n_embd = n_embd
        self.n_head = n_head
        self.dropout = dropout
        self.n_block = n_block

    def build(self, input_shape):
        self.block_size = input_shape[1]
        self.token_embedding_table = layers.Embedding(self.vocab_size, self.n_embd)
        self.position_embedding_table = layers.Embedding(self.block_size, self.n_embd)
        self.blocks = keras.Sequential([Block(self.n_embd, self.n_head, self.dropout) for _ in range(self.n_block)])
        self.ln_f = layers.LayerNormalization(epsilon=1e-5)
        self.lm_head = layers.Dense(self.vocab_size, activation=None)

    def call(self, idx, *args, **kwargs):
        # idx is of shape (B, T, C)

        tok_emb = self.token_embedding_table(idx) # (B,T,C)
        pos_emb = self.position_embedding_table(tf.range(0, self.block_size)) # (T,C)
        x = tok_emb + pos_emb # (B,T,C)
        x = self.blocks(x) # (B,T,C)
        x = self.ln_f(x) # (B,T,C)
        logits = self.lm_head(x) # (B,T,vocab_size)

        return logits

B, T, C = 32, 8, 5
head = Head(3, T, 0)
head.build((T, C))
x = tf.convert_to_tensor(np.random.random((B, T, C)))
head.call(x)