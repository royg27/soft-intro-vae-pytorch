# Copyright 2020-2021 Tal Daniel
# Copyright 2019-2020 Stanislav Pidhorskyi
#
# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
#
# This work is licensed under the Creative Commons Attribution-NonCommercial
# 4.0 International License. To view a copy of this license, visit
# http://creativecommons.org/licenses/by-nc/4.0/ or send a letter to
# Creative Commons, PO Box 1866, Mountain View, CA 94042, USA.

from net import *
from model import SoftIntroVAEModelTL
from launcher import run
from dataloader import *
from checkpointer import Checkpointer
from defaults import get_cfg_defaults
from PIL import Image
import PIL
import os


def millify(n):
    millnames = ['', 'k', 'M', 'G', 'T', 'P']
    n = float(n)
    millidx = max(0, min(len(millnames) - 1, int(math.floor(0 if n == 0 else math.log10(abs(n)) / 3))))

    return '{:.1f}{}'.format(n / 10 ** (3 * millidx), millnames[millidx])


def count_parameters(model, print_func=print, verbose=False):
    for n, p in model.named_parameters():
        if p.requires_grad and verbose:
            print_func(n, millify(p.numel()))
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def draw_uncurated_result_figure(cfg, png, model, cx, cy, cw, ch, rows, lods, seed):
    print(png)
    N = sum(rows * 2 ** lod for lod in lods)
    images = []

    rnd = np.random.RandomState(5)
    for i in range(N):
        latents = rnd.randn(1, cfg.MODEL.LATENT_SPACE_SIZE)
        samplez = torch.tensor(latents).float().cuda()
        image = model.generate(cfg.DATASET.MAX_RESOLUTION_LEVEL - 2, 1, samplez, 1, mixing=True)
        images.append(image[0])

    canvas = PIL.Image.new('RGB', (sum(cw // 2 ** lod for lod in lods), ch * rows), 'white')
    image_iter = iter(list(images))
    for col, lod in enumerate(lods):
        for row in range(rows * 2 ** lod):
            im = next(image_iter).cpu().numpy()
            im = im.transpose(1, 2, 0)
            im = im * 0.5 + 0.5
            image = PIL.Image.fromarray(np.clip(im * 255, 0, 255).astype(np.uint8), 'RGB')
            image = image.crop((cx, cy, cx + cw, cy + ch))
            image = image.resize((cw // 2 ** lod, ch // 2 ** lod), PIL.Image.ANTIALIAS)
            canvas.paste(image, (sum(cw // 2 ** lod for lod in lods[:col]), row * ch // 2 ** lod))
    canvas.save(png)


def sample(cfg, logger):
    torch.cuda.set_device(0)
    model = SoftIntroVAEModelTL(
        startf=cfg.MODEL.START_CHANNEL_COUNT,
        layer_count=cfg.MODEL.LAYER_COUNT,
        maxf=cfg.MODEL.MAX_CHANNEL_COUNT,
        latent_size=cfg.MODEL.LATENT_SPACE_SIZE,
        dlatent_avg_beta=cfg.MODEL.DLATENT_AVG_BETA,
        style_mixing_prob=cfg.MODEL.STYLE_MIXING_PROB,
        mapping_layers=cfg.MODEL.MAPPING_LAYERS,
        channels=cfg.MODEL.CHANNELS,
        generator=cfg.MODEL.GENERATOR,
        encoder=cfg.MODEL.ENCODER,
        beta_kl=cfg.MODEL.BETA_KL,
        beta_rec=cfg.MODEL.BETA_REC,
        beta_neg=cfg.MODEL.BETA_NEG[cfg.MODEL.LAYER_COUNT - 1],
        scale=cfg.MODEL.SCALE
    )

    model.cuda(0)
    model.eval()
    model.requires_grad_(False)

    decoder = model.decoder
    encoder = model.encoder
    mapping_tl = model.mapping_tl
    mapping_fl = model.mapping_fl

    dlatent_avg = model.dlatent_avg

    logger.info("Trainable parameters decoder:")
    print(count_parameters(decoder))

    logger.info("Trainable parameters encoder:")
    print(count_parameters(encoder))

    arguments = dict()
    arguments["iteration"] = 0

    model_dict = {
        'discriminator_s': encoder,
        'generator_s': decoder,
        'mapping_tl_s': mapping_tl,
        'mapping_fl_s': mapping_fl,
        'dlatent_avg': dlatent_avg
    }

    checkpointer = Checkpointer(cfg,
                                model_dict,
                                {},
                                logger=logger,
                                save=False)

    checkpointer.load()

    model.eval()

    im_size = 2 ** (cfg.MODEL.LAYER_COUNT + 1)
    seed = np.random.randint(0, 999999)
    print("seed:", seed)
    with torch.no_grad():
        path = './make_figures/output'
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, cfg.NAME), exist_ok=True)
        draw_uncurated_result_figure(cfg, './make_figures/output/%s/generations.jpg' % cfg.NAME,
                                     model, cx=0, cy=0, cw=im_size, ch=im_size, rows=6, lods=[0, 0, 0, 1, 1, 2], seed=seed)


if __name__ == "__main__":
    gpu_count = 1
    run(sample, get_cfg_defaults(), description='SoftIntroVAE-generations', default_config='./configs/ffhq256.yaml',
        world_size=gpu_count, write_log=False)