using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;

/// <summary>
/// Mini reader for Archipelago <c>.hydra</c> files (see worlds/hydra_plugin).
///
/// Layout (little-endian throughout):
///   magic[6] ("HYDRA1"), version u8, flags u8,
///   seed_len u16 + seed bytes (UTF-8, info only),
///   key_len u16 + key bytes (per-file random key, stored in the header),
///   nonce_len u16 + nonce bytes (per-file random),
///   payload_len u64 + payload bytes (raw-deflate compressed, then
///   XORed with SHA256(key || nonce || counter_be64) keystream).
/// Only BCL types are used (no NuGet packages).
/// </summary>
public sealed class HydraFile
{
    public const string Magic = "HYDRA1";
    public const byte CurrentVersion = 1;

    public string SeedName { get; private set; } = "";
    public byte[] Key { get; private set; } = Array.Empty<byte>();
    public byte[] Nonce { get; private set; } = Array.Empty<byte>();
    public byte Flags { get; private set; }

    /// <summary>Decrypted + decompressed JSON payload.</summary>
    public string Json { get; private set; } = "";

    public bool Compressed => (Flags & 0x01) != 0;
    public bool Encrypted => (Flags & 0x02) != 0;

    private HydraFile()
    {
    }

    public static HydraFile Read(string path)
    {
        using var stream = File.OpenRead(path);
        return Read(stream);
    }

    public static HydraFile Read(Stream stream)
    {
        var file = new HydraFile();
        using var reader = new BinaryReader(stream, Encoding.UTF8, leaveOpen: true);

        var magic = Encoding.ASCII.GetString(reader.ReadBytes(6));
        if (magic != Magic)
            throw new InvalidDataException("Not a .hydra file (bad magic).");

        var version = reader.ReadByte();
        if (version != CurrentVersion)
            throw new InvalidDataException($"Unsupported .hydra version {version}.");

        file.Flags = reader.ReadByte();
        file.SeedName = ReadString(reader);
        file.Key = ReadBlob(reader);
        file.Nonce = ReadBlob(reader);

        var payloadLen = reader.ReadUInt64();
        if (payloadLen > int.MaxValue)
            throw new InvalidDataException(".hydra payload too large.");
        var payload = reader.ReadBytes((int)payloadLen);
        if (payload.Length != (int)payloadLen)
            throw new EndOfStreamException("Truncated .hydra payload.");

        if (file.Encrypted)
            payload = Xor(payload, KeyStream(file.Key, file.Nonce, payload.Length));
        if (file.Compressed)
            payload = Inflate(payload);

        file.Json = Encoding.UTF8.GetString(payload);
        return file;
    }

    private static string ReadString(BinaryReader reader)
    {
        var len = reader.ReadUInt16();
        var buf = reader.ReadBytes(len);
        if (buf.Length != len)
            throw new EndOfStreamException("Truncated .hydra header.");
        return Encoding.UTF8.GetString(buf);
    }

    private static byte[] ReadBlob(BinaryReader reader)
    {
        var len = reader.ReadUInt16();
        var buf = reader.ReadBytes(len);
        if (buf.Length != len)
            throw new EndOfStreamException("Truncated .hydra header.");
        return buf;
    }

    private static byte[] KeyStream(byte[] key, byte[] nonce, int length)
    {
        using var sha = SHA256.Create();
        var output = new byte[length];
        int pos = 0;
        ulong counter = 0;
        while (pos < length)
        {
            var counterBytes = BitConverter.GetBytes(counter);
            if (BitConverter.IsLittleEndian)
                Array.Reverse(counterBytes); // file uses big-endian counter
            var input = new byte[key.Length + nonce.Length + 8];
            Buffer.BlockCopy(key, 0, input, 0, key.Length);
            Buffer.BlockCopy(nonce, 0, input, key.Length, nonce.Length);
            Buffer.BlockCopy(counterBytes, 0, input, key.Length + nonce.Length, 8);
            var block = sha.ComputeHash(input);
            var take = Math.Min(block.Length, length - pos);
            Buffer.BlockCopy(block, 0, output, pos, take);
            pos += take;
            counter++;
        }
        return output;
    }

    private static byte[] Xor(byte[] data, byte[] stream)
    {
        var output = new byte[data.Length];
        for (int i = 0; i < data.Length; i++)
            output[i] = (byte)(data[i] ^ stream[i]);
        return output;
    }

    private static byte[] Inflate(byte[] data)
    {
        // Python writes raw deflate (zlib wbits -15); DeflateStream reads exactly that.
        using var input = new MemoryStream(data, writable: false);
        using var deflate = new DeflateStream(input, CompressionMode.Decompress);
        using var output = new MemoryStream();
        deflate.CopyTo(output);
        return output.ToArray();
    }
}
